package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	_ "github.com/mattn/go-sqlite3"
	tdlib "github.com/zelenin/go-tdlib/client"
)

// Config menyimpan konfigurasi aplikasi
type Config struct {
	OwnerID      int64  `json:"owner_id"`
	RequiredChat int64  `json:"required_chat"`
	ApiID        int32  `json:"api_id"`
	ApiHash      string `json:"api_hash"`
}

// AppState menyimpan status aplikasi
type AppState struct {
	db         *sql.DB
	cfg        Config
	client     *tdlib.Client
	blacklist  *sync.Map
	whitelist  *sync.Map
	dbMutex    sync.RWMutex
	msgHandler chan *tdlib.Message
	logger     *log.Logger
}

// NewAppState membuat instance AppState baru
func NewAppState() *AppState {
	return &AppState{
		blacklist:  &sync.Map{},
		whitelist:  &sync.Map{},
		msgHandler: make(chan *tdlib.Message, 100), // Buffer untuk menangani pesan secara asinkron
		logger:     log.New(os.Stdout, "[BOT] ", log.LstdFlags),
	}
}

func main() {
	// Buat context yang dapat dibatalkan untuk kontrol shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Buat state aplikasi
	app := NewAppState()

	// Setup penanganan sinyal untuk shutdown yang bersih
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigChan
		app.logger.Printf("Menerima sinyal: %v, memulai shutdown...", sig)
		cancel()
	}()

	// Inisialisasi komponen aplikasi
	if err := app.loadConfig(); err != nil {
		app.logger.Fatalf("Gagal memuat konfigurasi: %v", err)
	}

	if err := app.initDB(); err != nil {
		app.logger.Fatalf("Gagal inisialisasi database: %v", err)
	}
	defer app.db.Close()

	if err := app.preloadLists(); err != nil {
		app.logger.Printf("Peringatan: gagal memuat daftar: %v", err)
	}

	if err := app.initTdlib(); err != nil {
		app.logger.Fatalf("Gagal inisialisasi TDLib: %v", err)
	}

	// Jalankan worker untuk menangani pesan
	go app.messageWorker(ctx)

	// Jalankan listener utama
	app.listener(ctx)

	// Tunggu konteks dibatalkan (dari penanganan sinyal)
	<-ctx.Done()
	app.logger.Println("Shutdown selesai")
}

// loadConfig memuat konfigurasi dari file
func (a *AppState) loadConfig() error {
	file, err := os.ReadFile("config.json")
	if err != nil {
		return fmt.Errorf("error membaca config: %w", err)
	}

	if err := json.Unmarshal(file, &a.cfg); err != nil {
		return fmt.Errorf("error parsing config: %w", err)
	}

	return nil
}

// initDB menginisialisasi koneksi database
func (a *AppState) initDB() error {
	var err error
	a.db, err = sql.Open("sqlite3", "data.db?_journal=WAL&_sync=NORMAL&_cache_size=5000")
	if err != nil {
		return fmt.Errorf("error koneksi database: %w", err)
	}

	// Konfigurasi koneksi database
	a.db.SetMaxOpenConns(1)        // SQLite hanya mendukung 1 writer
	a.db.SetMaxIdleConns(1)
	a.db.SetConnMaxLifetime(time.Hour)

	// Buat tabel jika belum ada
	_, err = a.db.Exec(`
		PRAGMA journal_mode = WAL;
		PRAGMA synchronous = NORMAL;
		PRAGMA cache_size = 5000;
		PRAGMA temp_store = MEMORY;
		CREATE TABLE IF NOT EXISTS blacklist (word TEXT PRIMARY KEY);
		CREATE TABLE IF NOT EXISTS whitelist (word TEXT PRIMARY KEY);
		CREATE INDEX IF NOT EXISTS idx_blacklist_word ON blacklist(word);
		CREATE INDEX IF NOT EXISTS idx_whitelist_word ON whitelist(word);
	`)

	if err != nil {
		return fmt.Errorf("error membuat tabel: %w", err)
	}

	return nil
}

// preloadLists memuat daftar hitam dan putih ke memori untuk performa
func (a *AppState) preloadLists() error {
	// Muat blacklist
	rows, err := a.db.Query("SELECT word FROM blacklist")
	if err != nil {
		return fmt.Errorf("error memuat blacklist: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var word string
		if err := rows.Scan(&word); err != nil {
			return fmt.Errorf("error scanning blacklist: %w", err)
		}
		a.blacklist.Store(word, true)
	}

	// Muat whitelist
	rows, err = a.db.Query("SELECT word FROM whitelist")
	if err != nil {
		return fmt.Errorf("error memuat whitelist: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var word string
		if err := rows.Scan(&word); err != nil {
			return fmt.Errorf("error scanning whitelist: %w", err)
		}
		a.whitelist.Store(word, true)
	}

	return nil
}

// initTdlib menginisialisasi klien TDLib
func (a *AppState) initTdlib() error {
	// Setup TDLib log
	tdlib.SetLogVerbosityLevel(1)
	
	// Konfigurasi TDLib
	opts := tdlib.Config{
		APIID:               a.cfg.ApiID,
		APIHash:             a.cfg.ApiHash,
		DatabaseDirectory:   "tdlib-db",
		FilesDirectory:      "tdlib-files",
		UseMessageDatabase:  true,
		UseSecretChats:      false,
		SystemLanguageCode:  "en",
		DeviceModel:         "Server",
		ApplicationVersion:  "1.0",
		UseTestDataCenter:   false,
		UseChatInfoDatabase: true,
	}

	// Buat klien TDLib
	a.client = tdlib.NewClient(tdlib.NewTdlibClient(opts))
	
	// Periksa status autentikasi
	authState, err := a.client.GetAuthorizationState()
	if err != nil {
		return fmt.Errorf("error memeriksa status autentikasi: %w", err)
	}

	if authState.GetAuthorizationStateEnum() != tdlib.AuthorizationStateReadyType {
		a.logger.Println("Perlu autentikasi TDLib, silakan jalankan autentikasi terpisah")
	}

	return nil
}

// listener menangani pembaruan dari TDLib
func (a *AppState) listener(ctx context.Context) {
	updates := a.client.GetListener().Updates
	a.logger.Println("Listener aktif, menunggu pembaruan...")

	for {
		select {
		case update := <-updates:
			switch u := update.(type) {
			case *tdlib.UpdateNewMessage:
				// Kirim pesan ke channel untuk diproses oleh worker
				select {
				case a.msgHandler <- u.Message:
					// Berhasil mengirim ke channel
				default:
					// Channel penuh, log dan lewati
					a.logger.Println("Peringatan: channel handler penuh, lewati pesan")
				}
			}
		case <-ctx.Done():
			a.logger.Println("Listener dimatikan")
			return
		}
	}
}

// messageWorker memproses pesan secara asinkron
func (a *AppState) messageWorker(ctx context.Context) {
	for {
		select {
		case msg := <-a.msgHandler:
			a.handleMessage(msg)
		case <-ctx.Done():
			a.logger.Println("Worker dimatikan")
			return
		}
	}
}

// handleMessage memproses pesan yang diterima
func (a *AppState) handleMessage(msg *tdlib.Message) {
	// Recover dari panic dalam handler untuk menjaga stabilitas
	defer func() {
		if r := recover(); r != nil {
			a.logger.Printf("Pulih dari panic dalam handler pesan: %v", r)
		}
	}()

	// Ekstrak data pesan
	chatID := msg.ChatID
	fromID := msg.SenderUserID
	text := ""

	// Deteksi tipe pesan dan ekstrak teks
	if m, ok := msg.Content.(*tdlib.MessageText); ok {
		text = m.Text.Text
	} else {
		// Bukan pesan teks, tidak perlu diproses
		return
	}

	// Perintah /start - periksa keanggotaan
	if text == "/start" {
		if !a.checkJoin(fromID) {
			a.sendJoinPrompt(chatID)
		} else {
			a.sendMainMenu(chatID)
		}
		return
	}

	// Filter antigcast
	if a.checkBlacklist(text) && !a.checkWhitelist(text) {
		a.deleteMsg(chatID, msg.ID)
		return
	}

	// Penanganan perintah
	if strings.HasPrefix(text, "/") {
		// Hapus pesan perintah untuk kebersihan
		a.deleteMsg(chatID, msg.ID)
		
		// Periksa apakah pengguna adalah admin
		isAdmin := (fromID == a.cfg.OwnerID) || a.checkAdmin(chatID, fromID)
		if !isAdmin {
			return
		}

		// Parse perintah dan argumen
		cmdParts := strings.SplitN(text, " ", 2)
		cmd := strings.TrimPrefix(cmdParts[0], "/")
		args := ""
		if len(cmdParts) > 1 {
			args = cmdParts[1]
		}

		// Proses perintah
		a.processCommand(chatID, msg.ID, fromID, cmd, args)
	}
}

// processCommand menangani perintah yang valid
func (a *AppState) processCommand(chatID, msgID, fromID int64, cmd, args string) {
	switch cmd {
	case "addbl":
		if args == "" {
			a.replyAndDelete(chatID, msgID, "Error: Tidak ada kata yang ditentukan")
			return
		}
		a.addWord("blacklist", args)
		a.replyAndDelete(chatID, msgID, "✅ Berhasil ditambahkan ke blacklist.")
	
	case "addwhite":
		if args == "" {
			a.replyAndDelete(chatID, msgID, "Error: Tidak ada kata yang ditentukan")
			return
		}
		a.addWord("whitelist", args)
		a.replyAndDelete(chatID, msgID, "✅ Berhasil ditambahkan ke whitelist.")
	
	case "bltext":
		list := a.getList("blacklist")
		if list == "" {
			list = "Daftar kosong"
		}
		a.send(chatID, "🔴 *Blacklist:*\n"+list)
	
	case "whitetext":
		list := a.getList("whitelist")
		if list == "" {
			list = "Daftar kosong"
		}
		a.send(chatID, "⚪ *Whitelist:*\n"+list)
	
	case "clean":
		if fromID != a.cfg.OwnerID {
			a.replyAndDelete(chatID, msgID, "⛔ Hanya owner yang dapat menggunakan perintah ini.")
			return
		}
		os.RemoveAll("tdlib-db")
		os.RemoveAll("tdlib-files")
		a.send(chatID, "🧹 Cache TDLib berhasil dibersihkan.\n⚠️ *Perlu restart bot.*")
	
	case "eval":
		if fromID != a.cfg.OwnerID {
			return // Abaikan saja untuk keamanan
		}
		result := a.evalCode(args)
		a.send(chatID, "```\n"+result+"\n```")
	
	case "help":
		a.sendHelpMenu(chatID)
	
	case "addme":
		a.send(chatID, "[➕ Tambahkan Saya ke Grup Anda](https://t.me/yourbot?startgroup=true)")
	
	case "developers":
		a.send(chatID, "[👨‍💻 Developers](https://t.me/developerlink)")
	
	case "support":
		a.send(chatID, "[💬 Support](https://t.me/supportlink)")
	
	case "stats":
		if fromID != a.cfg.OwnerID {
			return
		}
		var blCount, whCount int
		a.blacklist.Range(func(_, _ interface{}) bool {
			blCount++
			return true
		})
		a.whitelist.Range(func(_, _ interface{}) bool {
			whCount++
			return true
		})
		a.send(chatID, fmt.Sprintf("📊 *Statistik*\n\n🔴 Blacklist: %d kata\n⚪ Whitelist: %d kata", blCount, whCount))
	}
}

// checkJoin memeriksa apakah pengguna sudah bergabung ke channel yang diperlukan
func (a *AppState) checkJoin(userID int64) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	
	r, err := a.client.GetChatMember(&tdlib.GetChatMemberRequest{
		ChatID: a.cfg.RequiredChat, 
		UserID: userID,
	})
	
	if err != nil {
		a.logger.Printf("Error memeriksa keanggotaan: %v", err)
		return false
	}
	
	return r.Status == "member" || r.Status == "administrator" || r.Status == "creator"
}

// sendJoinPrompt mengirim pesan untuk bergabung ke channel yang diperlukan
func (a *AppState) sendJoinPrompt(chatID int64) {
	// Format link yang lebih baik
	inviteLink := fmt.Sprintf("https://t.me/c/%d", a.cfg.RequiredChat)
	text := "🔔 *Perlu Bergabung*\n\nSilakan join channel & group kami dulu sebelum menggunakan bot ini."
	a.send(chatID, text+"\n\n[🔗 Join Sekarang]("+inviteLink+")")
}

// sendMainMenu mengirim menu utama
func (a *AppState) sendMainMenu(chatID int64) {
	menu := "👋 *Selamat datang!*\n\n" +
		"Bot ini akan membantu Anda memfilter pesan yang tidak diinginkan.\n\n" +
		"Pilih menu:\n" +
		"📚 /help - Lihat perintah\n" +
		"➕ /addme - Tambah bot ke grup\n" +
		"👨‍💻 /developers - Info developer\n" +
		"💬 /support - Bantuan"
	
	a.send(chatID, menu)
}

// sendHelpMenu mengirim menu bantuan
func (a *AppState) sendHelpMenu(chatID int64) {
	help := "✅ *Bot Antigcast Tools*\n\n" +
		"*Perintah Admin:*\n" +
		"📝 /addbl `kata` - Tambah kata blacklist\n" +
		"📝 /addwhite `kata` - Tambah kata whitelist\n" +
		"📋 /bltext - Lihat daftar blacklist\n" +
		"📋 /whitetext - Lihat daftar whitelist\n" +
		"📊 /stats - Statistik (owner)\n" +
		"🧹 /clean - Bersihkan cache bot (owner)\n" +
		"⚙️ /eval - Eksekusi code (owner)\n\n" +
		"*Info:*\n" +
		"Pesan yang mengandung kata di blacklist akan dihapus kecuali mengandung kata di whitelist."

	a.send(chatID, help)
}

// checkAdmin memeriksa apakah pengguna adalah admin
func (a *AppState) checkAdmin(chatID, userID int64) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	
	r, err := a.client.GetChatMember(&tdlib.GetChatMemberRequest{
		ChatID: chatID, 
		UserID: userID,
	})
	
	if err != nil {
		a.logger.Printf("Error memeriksa admin: %v", err)
		return false
	}
	
	return r.Status == "administrator" || r.Status == "creator"
}

// deleteMsg menghapus pesan
func (a *AppState) deleteMsg(chatID, msgID int64) {
	a.client.DeleteMessages(&tdlib.DeleteMessagesRequest{
		ChatID:     chatID,
		MessageIDs: []int64{msgID},
		Revoke:     true,
	})
}

// replyAndDelete membalas pesan dan menghapusnya setelah beberapa saat
func (a *AppState) replyAndDelete(chatID, replyTo int64, text string) {
	// Tambahkan penanda waktu untuk menghindari throttling
	formattedText := text
	
	sent, err := a.client.SendMessage(&tdlib.SendMessageRequest{
		ChatID:          chatID,
		ReplyToMessageID: replyTo,
		InputMessageContent: tdlib.NewInputMessageText(
			&tdlib.FormattedText{Text: formattedText},
			true, // Mendukung markdown
			false,
		),
	})
	
	if err != nil {
		a.logger.Printf("Error mengirim pesan: %v", err)
		return
	}

	// Hapus pesan setelah delay
	go func() {
		time.Sleep(5 * time.Second)
		a.deleteMsg(chatID, sent.ID)
	}()
}

// send mengirim pesan
func (a *AppState) send(chatID int64, text string) {
	_, err := a.client.SendMessage(&tdlib.SendMessageRequest{
		ChatID: chatID,
		InputMessageContent: tdlib.NewInputMessageText(
			&tdlib.FormattedText{Text: text},
			true, // Mendukung markdown
			false,
		),
	})
	
	if err != nil {
		a.logger.Printf("Error mengirim pesan: %v", err)
	}
}

// addWord menambahkan kata ke daftar hitam atau putih
func (a *AppState) addWord(table, word string) {
	word = strings.ToLower(strings.TrimSpace(word))
	if word == "" {
		return
	}

	// Tambahkan ke database
	a.dbMutex.Lock()
	_, err := a.db.Exec("INSERT OR IGNORE INTO "+table+" (word) VALUES (?)", word)
	a.dbMutex.Unlock()
	
	if err != nil {
		a.logger.Printf("Error menambahkan kata: %v", err)
		return
	}

	// Tambahkan ke cache di memori
	if table == "blacklist" {
		a.blacklist.Store(word, true)
	} else {
		a.whitelist.Store(word, true)
	}
}

// getList mengambil daftar kata
func (a *AppState) getList(table string) string {
	a.dbMutex.RLock()
	rows, err := a.db.Query("SELECT word FROM " + table + " ORDER BY word")
	a.dbMutex.RUnlock()
	
	if err != nil {
		a.logger.Printf("Error mengambil daftar: %v", err)
		return "Error: tidak dapat mengambil daftar"
	}
	defer rows.Close()

	var list strings.Builder
	count := 0
	for rows.Next() {
		var word string
		if err := rows.Scan(&word); err != nil {
			continue
		}
		count++
		list.WriteString(fmt.Sprintf("%d. `%s`\n", count, word))
	}
	
	if count == 0 {
		return "Daftar kosong"
	}
	
	return list.String()
}

// checkBlacklist memeriksa apakah teks mengandung kata di daftar hitam
func (a *AppState) checkBlacklist(text string) bool {
	text = strings.ToLower(text)
	
	found := false
	a.blacklist.Range(func(key, _ interface{}) bool {
		word := key.(string)
		if strings.Contains(text, word) {
			found = true
			return false // berhenti mencari
		}
		return true // lanjut mencari
	})
	
	return found
}

// checkWhitelist memeriksa apakah teks mengandung kata di daftar putih
func (a *AppState) checkWhitelist(text string) bool {
	text = strings.ToLower(text)
	
	found := false
	a.whitelist.Range(func(key, _ interface{}) bool {
		word := key.(string)
		if strings.Contains(text, word) {
			found = true
			return false // berhenti mencari
		}
		return true // lanjut mencari
	})
	
	return found
}

// evalCode mengevaluasi kode secara aman
func (a *AppState) evalCode(code string) string {
	// Implementasi evaluasi sederhana
	// Dalam praktiknya, ini bisa berisi fungsi untuk debugging
	return fmt.Sprintf("Kode: %s\n\nCatatan: Ini adalah implementasi evaluasi sederhana untuk keamanan.", code)
}