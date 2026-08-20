from app.presenters.base import BasePresenter
from integrations.recall_ai.models import RecallAIBotStatusCodes, RecallAIBotStatusSubCodes, RecallAIMeeting


class RecallAIBotStatusPresenter(BasePresenter[RecallAIMeeting]):
    status: str = ""
    sub_status: str = ""

    @classmethod
    async def create(
        cls,
        recall_meeting: RecallAIMeeting,
    ):
        return cls(recall_meeting, status=recall_meeting.bot_status, sub_status=recall_meeting.bot_sub_status)

    @property
    def is_failed(self):
        if self.status == RecallAIBotStatusCodes.FATAL:
            return True
        if self.status == RecallAIBotStatusCodes.DONE:
            return not self.is_successful
        return False

    @property
    def is_successful(self):
        return self.status == RecallAIBotStatusCodes.DONE and self.sub_status in self.successful_done_sub_statuses

    @property
    def successful_done_sub_statuses(self) -> list[RecallAIBotStatusSubCodes]:
        return [
            RecallAIBotStatusSubCodes.CALL_ENDED_BY_HOST,
            RecallAIBotStatusSubCodes.CALL_ENDED_BY_PLATFORM_IDLE,
            RecallAIBotStatusSubCodes.CALL_ENDED_BY_PLATFORM_MAX_LENGTH,
            RecallAIBotStatusSubCodes.TIMEOUT_EXCEEDED_EVERYONE_LEFT,
            RecallAIBotStatusSubCodes.TIMEOUT_EXCEEDED_SILENCE_DETECTED,
            RecallAIBotStatusSubCodes.TIMEOUT_EXCEEDED_MAX_DURATION,
            RecallAIBotStatusSubCodes.BOT_KICKED_FROM_CALL,
            RecallAIBotStatusSubCodes.BOT_RECEIVED_LEAVE_CALL,
        ]
