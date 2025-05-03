// Bot Telegram Antigcast (go-tdlib + goroutines)
// Powerful version!

package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	tdlib "github.com/zelenin/go-tdlib/client"
	_ "github.com/mattn/go-sqlite3"
)

type Config struct {
	OwnerID      int64  `json:"owner_id"`
	RequiredChat int64  `json:"required_chat"`
	ApiID        int32  `json:"api_id"`
	ApiHash      string `json:"api_hash"`
}

var (
	db     *sql.DB
	cfg    Config
	client *tdlib.Client
	mutex  sync.Mutex
)

func main() {
	loadConfig()
	initDB()
	initTdlib()

	listener()
}

func loadConfig() {
	file, err := os.ReadFile("config.json")
	if err != nil {
		log.Fatal("Config error:", err)
	}
	json.Unmarshal(file, &cfg)
}

func initDB() {
	var err error
	db, err = sql.Open("sqlite3", "data.db")
	if err != nil {
		log.Fatal(err)
	}
	db.Exec("CREATE TABLE IF NOT EXISTS blacklist (word TEXT PRIMARY KEY)")
	db.Exec("CREATE TABLE IF NOT EXISTS whitelist (word TEXT PRIMARY KEY)")
}

func initTdlib() {
	opts := tdlib.Config{
		APIID:               cfg.ApiID,
		APIHash:             cfg.ApiHash,
		DatabaseDirectory:  "tdlib-db",
		FilesDirectory:     "tdlib-files",
		UseMessageDatabase: true,
		UseSecretChats:     false,
		SystemLanguageCode: "en",
		DeviceModel:        "Server",
		ApplicationVersion: "1.0",
	}

	client = tdlib.NewClient(tdlib.NewTdlibClient(opts))
}

func listener() {
	for update := range client.GetListener().Updates {
		switch u := update.(type) {
		case *tdlib.UpdateNewMessage:
			go handleMessage(u.Message)
		}
	}
}

func handleMessage(msg *tdlib.Message) {
	chatID := msg.ChatID
	fromID := msg.SenderUserID
	text := msg.Content.(*tdlib.MessageText).Text.Text

	// Filter antigcast
	if checkBlacklist(text) && !checkWhitelist(text) {
		deleteMsg(chatID, msg.ID)
		return
	}

	// Command handling
	if strings.HasPrefix(text, "/") {
		deleteMsg(chatID, msg.ID)
		isAdmin := (fromID == cfg.OwnerID) || checkAdmin(chatID, fromID)
		if !isAdmin {
			return
		}

		split := strings.SplitN(text, " ", 2)
		cmd := strings.TrimPrefix(split[0], "/")
		args := ""
		if len(split) > 1 {
			args = split[1]
		}

		switch cmd {
		case "addbl":
			addWord("blacklist", args)
			replyAndDelete(chatID, msg.ID, "Berhasil ditambahkan ke blacklist.")
		case "addwhite":
			addWord("whitelist", args)
			replyAndDelete(chatID, msg.ID, "Berhasil ditambahkan ke whitelist.")
		case "bltext":
			send(chatID, "Blacklist:\n"+getList("blacklist"))
		case "whitetext":
			send(chatID, "Whitelist:\n"+getList("whitelist"))
		}
	}
}

func checkAdmin(chatID, userID int64) bool {
	r, _ := client.GetChatMember(&tdlib.GetChatMemberRequest{ChatID: chatID, UserID: userID})
	return r.Status == "administrator" || r.Status == "creator"
}

func deleteMsg(chatID, msgID int64) {
	client.DeleteMessages(&tdlib.DeleteMessagesRequest{
		ChatID: chatID,
		MessageIDs: []int64{msgID},
		Revoke:   true,
	})
}

func replyAndDelete(chatID, replyTo int64, text string) {
	sent, _ := client.SendMessage(&tdlib.SendMessageRequest{
		ChatID: chatID,
		ReplyToMessageID: replyTo,
		InputMessageContent: tdlib.NewInputMessageText(&tdlib.FormattedText{Text: text}, false, false),
	})

	go func() {
		time.Sleep(2 * time.Second)
		deleteMsg(chatID, sent.ID)
	}()
}

func send(chatID int64, text string) {
	client.SendMessage(&tdlib.SendMessageRequest{
		ChatID: chatID,
		InputMessageContent: tdlib.NewInputMessageText(&tdlib.FormattedText{Text: text}, false, false),
	})
}

func addWord(table, word string) {
	mutex.Lock()
	db.Exec("INSERT OR IGNORE INTO "+table+" (word) VALUES (?)", strings.ToLower(word))
	mutex.Unlock()
}

func getList(table string) string {
	mutex.Lock()
	rows, _ := db.Query("SELECT word FROM " + table)
	mutex.Unlock()
	defer rows.Close()

	var list string
	for rows.Next() {
		var word string
		rows.Scan(&word)
		list += "- " + word + "\n"
	}
	return list
}

func checkBlacklist(text string) bool {
	mutex.Lock()
	rows, _ := db.Query("SELECT word FROM blacklist")
	mutex.Unlock()
	defer rows.Close()

	for rows.Next() {
		var word string
		rows.Scan(&word)
		if strings.Contains(strings.ToLower(text), word) {
			return true
		}
	}
	return false
}

func checkWhitelist(text string) bool {
	mutex.Lock()
	rows, _ := db.Query("SELECT word FROM whitelist")
	mutex.Unlock()
	defer rows.Close()

	for rows.Next() {
		var word string
		rows.Scan(&word)
		if strings.Contains(strings.ToLower(text), word) {
			return true
		}
	}
	return false
}
