export interface WorkspaceAccessRequestProps {
  workspaceId: string
  backUrl: string
}

export interface AccessRequest {
  id: string
  created_at: string
}

export interface WorkspaceAccessRequestState {
  workspace_id: string
  resource_label: string
  request: AccessRequest | null
}

export interface WorkspaceAccessRequestSubmitResponse {
  request: AccessRequest
  redirect_url: string | null
}
