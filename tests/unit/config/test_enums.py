from config.enums import ChannelEventAction, EmailDraftAction


def test_email_draft_action_mirrors_channel_event_action():
    # Channel handlers translate EmailDraftAction (broadcast payload) into
    # ChannelEventAction (wire payload to React). They're kept in lockstep by hand,
    # which means a future lifecycle action added to one is easy to forget on the
    # other. This test fails loudly when that happens.
    #
    # TS-side parity (app/javascript/types/channels.ts) is out of scope here — that
    # would need a generated-types check; this only guards the two Python enums.
    for member in EmailDraftAction:
        twin = ChannelEventAction[member.name]
        assert twin.value == member.value, (
            f"EmailDraftAction.{member.name}={member.value!r} drifted from "
            f"ChannelEventAction.{twin.name}={twin.value!r}"
        )
