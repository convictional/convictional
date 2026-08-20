import type { Post, PostComment, PostShowResponse, User } from "~/react/shared/types"

export function buildUser(overrides: Partial<User> = {}): User {
  return { id: "user-1", display_name: "Alice", picture: null, ...overrides }
}

export function buildComment(overrides: Partial<PostComment> = {}): PostComment {
  return {
    id: "comment-1",
    global_id: "gid://convictional/PostComment/comment-1",
    content: "Hello world",
    parent_id: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    user: buildUser(),
    reactions: {},
    replies: [],
    link_preview: null,
    ...overrides,
  }
}

export function buildPostDetail(overrides: Partial<Post> = {}): Post {
  return {
    id: "post-1",
    title: "A post",
    creator: buildUser(),
    group: null,
    workspace_id: "ws-1",
    is_announcement: false,
    is_pinned: false,
    pinned_at: null,
    content_preview: null,
    link_preview: null,
    comment_count: 0,
    new_comment_count: 0,
    last_commented_at: null,
    participants: [],
    permissions: { edit: true, pin: false, delete: true },
    ...overrides,
  }
}

export function buildShowResponse(overrides: Partial<PostShowResponse> = {}): PostShowResponse {
  return {
    post: buildPostDetail(),
    original_comment: buildComment({ id: "original-1", content: "Post body" }),
    top_level_comments: [],
    last_visit_at: null,
    mailbox_entry: null,
    subscription: { wants_all: false, is_explicit: false },
    ...overrides,
  }
}
