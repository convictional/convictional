import re
import time
from pathlib import Path

from lib.email_reply_parser import EmailMessage

EMAILS_DIR = Path(__file__).parents[2] / "fixtures" / "emails"


def get_email(name: str) -> EmailMessage:
    text = (EMAILS_DIR / f"{name}.txt").read_text()
    return EmailMessage(text).read()


def test_simple_body():
    message = get_email("email_1_1")

    assert len(message.fragments) == 3
    assert [f.signature for f in message.fragments] == [False, True, True]
    assert [f.hidden for f in message.fragments] == [False, True, True]
    assert "folks" in message.fragments[0].content
    assert "riak-users" in message.fragments[2].content


def test_reads_bottom_message():
    message = get_email("email_1_2")

    assert len(message.fragments) == 6
    assert [f.quoted for f in message.fragments] == [False, True, False, True, False, False]
    assert [f.signature for f in message.fragments] == [False, False, False, False, False, True]
    assert [f.hidden for f in message.fragments] == [False, False, False, True, True, True]
    assert "Hi," in message.fragments[0].content
    assert "On" in message.fragments[1].content
    assert ">" in message.fragments[3].content
    assert "riak-users" in message.fragments[5].content


def test_reads_inline_replies():
    message = get_email("email_1_8")

    assert len(message.fragments) == 7
    assert [f.quoted for f in message.fragments] == [True, False, True, False, True, False, False]
    assert [f.signature for f in message.fragments] == [False, False, False, False, False, False, True]
    assert [f.hidden for f in message.fragments] == [False, False, False, False, True, True, True]


def test_reads_top_post():
    message = get_email("email_1_3")
    assert len(message.fragments) == 5


def test_multiline_reply_headers():
    message = get_email("email_1_6")
    assert "I get" in message.fragments[0].content
    assert "On" in message.fragments[1].content


def test_captures_date_string():
    message = get_email("email_1_4")
    assert "Awesome" in message.fragments[0].content
    assert "On" in message.fragments[1].content
    assert "Loader" in message.fragments[1].content


def test_complex_body_with_one_fragment():
    message = get_email("email_1_5")
    assert len(message.fragments) == 1


def test_verify_reads_signature_correct():
    message = get_email("correct_sig")

    assert len(message.fragments) == 2
    assert [f.quoted for f in message.fragments] == [False, False]
    assert [f.signature for f in message.fragments] == [False, True]
    assert [f.hidden for f in message.fragments] == [False, True]
    assert "--" in message.fragments[1].content


def test_deals_with_windows_line_endings():
    msg = get_email("email_1_7")
    assert ":+1:" in msg.fragments[0].content
    assert "On" in msg.fragments[1].content
    assert "Steps 0-2" in msg.fragments[1].content


def test_reply_is_parsed():
    message = get_email("email_1_2")
    assert "You can list the keys for the bucket" in message.reply


def test_reply_from_gmail():
    text = (EMAILS_DIR / "email_gmail.txt").read_text()
    assert EmailMessage(text).read().reply == "This is a test for inbox replying to a github message."


def test_parse_out_just_top_for_outlook_reply():
    text = (EMAILS_DIR / "email_2_1.txt").read_text()
    assert EmailMessage(text).read().reply == "Outlook with a reply"


def test_parse_out_just_top_for_outlook_with_reply_directly_above_line():
    text = (EMAILS_DIR / "email_2_2.txt").read_text()
    assert EmailMessage(text).read().reply == "Outlook with a reply directly above line"


def test_parse_out_just_top_for_outlook_with_unusual_headers_format():
    text = (EMAILS_DIR / "email_2_3.txt").read_text()
    assert EmailMessage(text).read().reply == "Outlook with a reply above headers using unusual format"


def test_sent_from_iphone():
    text = (EMAILS_DIR / "email_iPhone.txt").read_text()
    assert "Sent from my iPhone" not in EmailMessage(text).read().reply


def test_email_one_is_not_on():
    text = (EMAILS_DIR / "email_one_is_not_on.txt").read_text()
    assert "On Oct 1, 2012, at 11:55 PM, Dave Tapley wrote:" not in EmailMessage(text).read().reply


def test_partial_quote_header():
    message = get_email("email_partial_quote_header")
    assert "On your remote host you can run:" in message.reply
    assert "telnet 127.0.0.1 52698" in message.reply
    assert "This should connect to TextMate" in message.reply


def test_email_headers_no_delimiter():
    message = get_email("email_headers_no_delimiter")
    assert message.reply.strip() == "And another reply!"


def test_multiple_on():
    message = get_email("greedy_on")

    assert re.match("^On your remote host", message.fragments[0].content)
    assert re.match("^On 9 Jan 2014", message.fragments[1].content)
    assert [f.quoted for f in message.fragments] == [False, True, False]
    assert [f.signature for f in message.fragments] == [False, False, False]
    assert [f.hidden for f in message.fragments] == [False, True, True]


def test_pathological_emails():
    t0 = time.time()
    get_email("pathological")
    assert time.time() - t0 < 1, "Took too long"


def test_doesnt_remove_signature_delimiter_in_mid_line():
    message = get_email("email_sig_delimiter_in_middle_of_line")
    assert len(message.fragments) == 1
