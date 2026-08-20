from integrations.recall_ai.models import RecallAIBotOptions, RecallAIBotStatusCodes


def test_recall_ai_bot_options_images():
    options = RecallAIBotOptions(meeting_url="https://example.com")

    assert RecallAIBotStatusCodes.IN_CALL_NOT_RECORDING.value in options.automatic_video_output
    assert RecallAIBotStatusCodes.IN_CALL_RECORDING.value in options.automatic_video_output
    assert "b64_data" in options.automatic_video_output[RecallAIBotStatusCodes.IN_CALL_RECORDING.value]
    assert "b64_data" in options.automatic_video_output[RecallAIBotStatusCodes.IN_CALL_NOT_RECORDING.value]
    assert len(options.automatic_video_output[RecallAIBotStatusCodes.IN_CALL_NOT_RECORDING.value]["b64_data"]) > 0
    assert len(options.automatic_video_output[RecallAIBotStatusCodes.IN_CALL_RECORDING.value]["b64_data"]) > 0
