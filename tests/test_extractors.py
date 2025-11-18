import datetime as dt
from daily_contacts import EMAIL_REGEX, extract_emails_from_html, AuthorContact


def test_email_regex_basic():
    text = "Contact: alice@example.com or bob.smith@tsinghua.edu.cn"
    emails = EMAIL_REGEX.findall(text)
    assert "alice@example.com" in emails
    assert "bob.smith@tsinghua.edu.cn" in emails


def test_extract_emails_deduplicates():
    html = "<a>alice@example.com</a><span>alice@example.com</span>"
    emails = extract_emails_from_html(html)
    assert emails == ["alice@example.com"]


def test_contact_key_prefers_email():
    contact = AuthorContact(
        name="Alice",
        affiliation="DeepSeek",
        email="alice@deepseek.com",
        source="arxiv",
        source_url="https://arxiv.org/abs/1234",
        last_seen=dt.datetime.now(dt.timezone.utc),
    )
    assert contact.key() == "alice@deepseek.com"

