from config.sentry import scrub_sensitive_data


class TestSentryScrubbing:
    def test_scrub_direct_field_names(self):
        """Test that direct sensitive field names are redacted."""
        data = {
            "subject": "Secret email subject",
            "body_plain": "Confidential message content",
            "body_html": "<p>Secret HTML</p>",
            "body_markdown": "# Secret Markdown",
            "preview": "Secret preview",
            "title": "Private thread title",
            "last_comment": "Private comment",
            "safe_field": "This should not be redacted",
            "user_id": "uuid-123",
        }

        result = scrub_sensitive_data(data)

        assert result["subject"] == "[REDACTED]"
        assert result["body_plain"] == "[REDACTED]"
        assert result["body_html"] == "[REDACTED]"
        assert result["body_markdown"] == "[REDACTED]"
        assert result["preview"] == "[REDACTED]"
        assert result["title"] == "[REDACTED]"
        assert result["last_comment"] == "[REDACTED]"
        assert result["safe_field"] == "This should not be redacted"
        assert result["user_id"] == "uuid-123"

    def test_scrub_case_insensitive(self):
        """Test that field name matching is case insensitive."""
        data = {
            "Subject": "Secret subject",
            "BODY_PLAIN": "Secret body",
            "Title": "Secret title",
        }

        result = scrub_sensitive_data(data)

        assert result["Subject"] == "[REDACTED]"
        assert result["BODY_PLAIN"] == "[REDACTED]"
        assert result["Title"] == "[REDACTED]"

    def test_scrub_nested_structures(self):
        """Test scrubbing in deeply nested data structures."""
        data = {
            "exception": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [
                                {
                                    "vars": {
                                        "email_message": {
                                            "subject": "Sensitive subject",
                                            "body_html": "<p>Secret content</p>",
                                            "id": "safe-uuid-123",
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
            "breadcrumbs": [{"message": "Processing", "data": {"title": "Secret title"}}],
        }

        result = scrub_sensitive_data(data)

        # Check nested scrubbing
        email_msg = result["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["email_message"]
        assert email_msg["subject"] == "[REDACTED]"
        assert email_msg["body_html"] == "[REDACTED]"
        assert email_msg["id"] == "safe-uuid-123"

        # Check breadcrumb scrubbing
        assert result["breadcrumbs"][0]["data"]["title"] == "[REDACTED]"

    def test_scrub_list_structures(self):
        """Test scrubbing in list structures."""
        data = [
            {"subject": "Secret 1", "id": "safe-1"},
            {"nested": {"preview": "Confidential preview"}},
            ["inner_list", {"title": "Secret inner content"}],
        ]

        result = scrub_sensitive_data(data)

        assert result[0]["subject"] == "[REDACTED]"
        assert result[0]["id"] == "safe-1"
        assert result[1]["nested"]["preview"] == "[REDACTED]"
        assert result[2][1]["title"] == "[REDACTED]"

    def test_scrub_tuple_structures(self):
        """Test scrubbing in tuple structures."""
        data = (
            {"subject": "Secret tuple subject"},
            ("nested_tuple", {"body_plain": "Secret tuple body"}),
        )

        result = scrub_sensitive_data(data)

        assert result[0]["subject"] == "[REDACTED]"
        assert result[1][1]["body_plain"] == "[REDACTED]"

    def test_scrub_non_string_values_unchanged(self):
        """Test that non-string, non-dict, non-list values are unchanged."""
        data = {
            "number": 42,
            "boolean": True,
            "none_value": None,
            "subject": "Secret subject",  # This should be redacted
        }

        result = scrub_sensitive_data(data)

        assert result["number"] == 42
        assert result["boolean"] is True
        assert result["none_value"] is None
        assert result["subject"] == "[REDACTED]"

    def test_scrub_empty_structures(self):
        """Test scrubbing handles empty structures correctly."""
        data = {
            "empty_dict": {},
            "empty_list": [],
            "empty_string": "",
            "subject": "Secret",
        }

        result = scrub_sensitive_data(data)

        assert result["empty_dict"] == {}
        assert result["empty_list"] == []
        assert result["empty_string"] == ""
        assert result["subject"] == "[REDACTED]"

    def test_scrub_realistic_sentry_event(self):
        """Test scrubbing on a realistic Sentry event structure."""
        sentry_event = {
            "event_id": "abc123",
            "timestamp": "2024-01-01T00:00:00Z",
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": "Invalid email data processing",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "email.py",
                                    "function": "process_email",
                                    "vars": {
                                        "message": {
                                            "subject": "Confidential email subject",
                                            "body_plain": "Private email content",
                                            "sender": "user@example.com",
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ]
            },
            "extra": {"title": "Secret thread title", "message_count": 5},
        }

        result = scrub_sensitive_data(sentry_event)

        # Check metadata is preserved
        assert result["event_id"] == "abc123"
        assert result["timestamp"] == "2024-01-01T00:00:00Z"

        # Check vars are scrubbed
        message_vars = result["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["message"]
        assert message_vars["subject"] == "[REDACTED]"
        assert message_vars["body_plain"] == "[REDACTED]"
        assert message_vars["sender"] == "user@example.com"  # Not sensitive

        # Check extra field scrubbing
        assert result["extra"]["title"] == "[REDACTED]"
        assert result["extra"]["message_count"] == 5
