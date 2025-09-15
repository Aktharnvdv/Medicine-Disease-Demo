import imaplib, email, ssl
from pathlib import Path
from typing   import Iterable
from email    import message_from_bytes, policy
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

# ─── UPDATE THESE VALUES ────────────────────────────────────
IMAP_HOST  = "imap.gmail.com"        # Gmail IMAP server
USERNAME   = "XXXXXXXXXXXXXXX@gmail.com"   # <-- your address
APP_PASS   = "XXXXXXXXXXXXXXXXXXX"      # 16-char Gmail app password
MAILBOX    = "INBOX"                 # IMAP folder to search
SEARCH_CRITERIA = "SEEN"           # IMAP search string
ATTACH_DIR = Path("attachments")     # output directory
MAX_MSGS = 10
# ────────────────────────────────────────────────────────────

def get_body(msg: email.message.EmailMessage,
             prefer_html: bool = False) -> str:
    want = ("html",) if prefer_html else ("plain",)
    part = msg.get_body(preferencelist=want) or msg.get_body()
    return part.get_content() if part else ""


def save_attachments(msg: email.message.EmailMessage,
                     dest: Path = ATTACH_DIR) -> Iterable[Path]:
    dest.mkdir(exist_ok=True)
    for part in msg.iter_attachments():
        name = part.get_filename() or f"part-{part.get_content_type().replace('/', '_')}"
        safe = Path(name).name
        path = dest / safe

        content = part.get_payload(decode=True)      # ↩︎ bytes, never EmailMessage
        with path.open("wb") as f:
            f.write(content)

        yield path


def main() -> None:
    ctx = ssl.create_default_context()
    with imaplib.IMAP4_SSL(IMAP_HOST, ssl_context=ctx) as imap:
        imap.login(USERNAME, APP_PASS)
        imap.select(MAILBOX)

        typ, ids = imap.search(None, SEARCH_CRITERIA)
        if typ != "OK" or not ids or not ids[0]:
            print("No matching messages.")
            return

        for msg_id in ids[0].split()[:MAX_MSGS]:
            _, raw = imap.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1], policy=email.policy.default)

            print("\n" + "─" * 60)
            print("From   :", msg["From"])
            print("Subject:", msg["Subject"])

            body = get_body(msg)
            preview = body.replace("\n", " ")[:120]
            print("Body   :", preview + ("…" if len(body) > 120 else ""))

            for p in save_attachments(msg):
                print("Saved attachment:", p)

            imap.store(msg_id, "+FLAGS", "\\Seen")   # mark read


if __name__ == "__main__":
    main()
