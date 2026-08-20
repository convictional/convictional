from config.enums import GoalStatus


class GoalStatusMap:
    """
    Helper class for goal status information.
    Provides consistent status display data across templates.
    """

    STATUS_MAP = {
        GoalStatus.ON_TRACK.value: {
            "value": GoalStatus.ON_TRACK.value,
            "text": "On Track",
            "classes": "bg-success/30 text-success-content border-success-content/20",
            "dotClass": "bg-success-content",
            "icon": "dot",
        },
        GoalStatus.AT_RISK.value: {
            "value": GoalStatus.AT_RISK.value,
            "text": "At Risk",
            "classes": "bg-warning/30 text-warning-content border-warning-content/20",
            "dotClass": "bg-warning-content",
            "icon": "dot",
        },
        GoalStatus.OFF_TRACK.value: {
            "value": GoalStatus.OFF_TRACK.value,
            "text": "Off Track",
            "classes": "bg-error/30 text-error-content border-error-content/20",
            "dotClass": "bg-error-content",
            "icon": "dot",
        },
    }

    @classmethod
    def get_status_map(cls):
        """Returns the mapping of goal statuses to their display properties."""
        return cls.STATUS_MAP

    @classmethod
    def get_status_object(cls, status: GoalStatus | None = None, is_completed: bool = False):
        """
        Returns the display properties for a status.
        When is_completed=True, returns 'Complete' status regardless of the status parameter.
        """
        if is_completed:
            return {
                "value": "complete",
                "text": "Complete",
                "classes": "text-success-content",
                "dotClass": "bg-success-content",
                "icon": "check",
            }
        if status is None:
            status = GoalStatus.ON_TRACK
        return cls.STATUS_MAP.get(status.value, cls.STATUS_MAP[GoalStatus.ON_TRACK.value])
