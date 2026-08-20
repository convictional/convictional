from app.models.accounts import User


def user_avatar_url(user: User | None) -> str | None:
    # Returns a stable URL templates and JSON serializers can render synchronously.
    # Uploaded avatars route through the `user_avatar` endpoint so the GCS signed URL
    # can be resolved server-side (async credential refresh isn't possible during a
    # sync Jinja render). The path is hardcoded rather than resolved via
    # `request.url_for(...)` because importlinter forbids `app.helpers` from importing
    # `app.routers`, and the channels/MCP call sites don't have a request to thread.
    if user is None:
        return None
    if user.avatar_file_id is None:
        return user.oauth_picture
    # The endpoint serves a 302 to the avatar with Cache-Control: max-age=300, and the
    # path is otherwise stable, so a replaced avatar would keep showing the cached image
    # for up to five minutes. Key a version param on avatar_file_id (a new file id every
    # upload) so the URL changes whenever the avatar does, busting the cache everywhere
    # the avatar renders (settings page, nav, people lists).
    return f"/profile/{user.id}/avatar?v={user.avatar_file_id}"
