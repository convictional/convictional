import type { PostDraft } from "~/react/features/postsIndex/types"
import type { Post, User } from "~/react/shared/types"

export function makeUser(overrides: Partial<User> = {}): User {
  return { id: "user-1", display_name: "Alice", picture: null, ...overrides }
}

export function makePost(overrides: Partial<Post> = {}): Post {
  return {
    id: "post-1",
    title: "A post",
    creator: makeUser(),
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

export function makeDraft(overrides: Partial<PostDraft> = {}): PostDraft {
  return {
    id: "draft-1",
    title: "A draft",
    creator: makeUser(),
    collaborators: [],
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  }
}
