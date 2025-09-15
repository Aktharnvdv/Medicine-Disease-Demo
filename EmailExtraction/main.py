import imaplib, email, ssl
from pathlib import Path
from typing import Iterable

# ─── UPDATE THESE VALUES ────────────────────────────────────
IMAP_HOST  = "imap.gmail.com"        # Gmail IMAP server
USERNAME   = "akthercmr@gmail.com"   # <-- your address
APP_PASS   = "xxxxxxxxxxxxxxxx"      # 16-char Gmail app password
MAILBOX    = "INBOX"                 # IMAP folder to search
SEARCH_CRITERIA = "UNSEEN"           # IMAP search string
ATTACH_DIR = Path("attachments")     # output directory
# ────────────────────────────────────────────────────────────

def get_body(msg: email.message.EmailMessage, prefer_html: bool = False) -> str:
    """Return the best available body as a string, auto-decoded."""
    want = ("html",) if prefer_html else ("plain",)
    part = msg.get_body(preferencelist=want) or msg.get_body()
    return part.get_content() if part else ""

def save_attachments(msg: email.message.EmailMessage,
                     dest: Path = ATTACH_DIR) -> Iterable[Path]:
    """Save every attachment, yielding Path objects of saved files."""
    dest.mkdir(exist_ok=True)
    for part in msg.iter_attachments():
        name = part.get_filename() or f"part-{part.get_content_type().replace('/', '_')}"
        safe = Path(name).name                   # strips path tricks
        out_path = dest / safe
        with open(out_path, "wb") as f:
            f.write(part.get_content())          # already decoded
        yield out_path

def main() -> None:
    ctx = ssl.create_default_context()
    with imaplib.IMAP4_SSL(IMAP_HOST, ssl_context=ctx) as imap:
        imap.login(USERNAME, APP_PASS)
        imap.select(MAILBOX)
        typ, ids = imap.search(None, SEARCH_CRITERIA)
        if typ != "OK" or not ids or not ids[0]:
            print("No matching messages.")
            return

        for msg_id in ids[0].split():
            _, raw = imap.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1], policy=email.policy.default)

            print("\n" + "─" * 60)
            print("From   :", msg["From"])
            print("Subject:", msg["Subject"])
            preview = get_body(msg)[:120].replace("\n", " ")
            print("Body   :", preview + ("…" if len(preview) == 120 else ""))

            for path in save_attachments(msg):
                print("Saved attachment:", path)

            # Optional: mark the message as seen
            imap.store(msg_id, "+FLAGS", "\\Seen")

if __name__ == "__main__":
    main()
