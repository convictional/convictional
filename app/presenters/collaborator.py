from app.models.collaboration.workspace import Collaborator, Workspace, WorkspaceMixin, WorkspaceResourceFetcher
from app.presenters.base import BasePresenter


class CollaboratorPresenter(BasePresenter[Collaborator]):
    workspace: Workspace
    resource: WorkspaceMixin

    @property
    def is_removable(self):
        return self.resource.collaboration.is_removable(self.model.user_id)


class CollaboratorsPresenter(list[CollaboratorPresenter]):
    pending: list[CollaboratorPresenter]

    @classmethod
    async def create(cls, workspace: Workspace):
        all_collaborators: list[Collaborator] = (
            await Collaborator.unscoped.get_queryset()
            .filter(workspace_id=workspace.id)
            .prefetch_related("user__avatar_file")
            .all()
        )
        approved_collaborators = [c for c in all_collaborators if c.status.is_approved]

        await WorkspaceResourceFetcher(workspaces=[workspace]).fetch()

        collaborator_presenters = await cls._build_collaborators(approved_collaborators, workspace)

        result = cls(collaborator_presenters)
        result.pending = await cls._get_pending_collaborators(workspace, all_collaborators)
        return result

    @classmethod
    async def _get_pending_collaborators(cls, workspace: Workspace, all_collaborators: list[Collaborator]):
        pending_collaborators = [c for c in all_collaborators if c.status.is_pending]
        pending_collaborator_presenters = []
        if pending_collaborators:
            pending_collaborator_presenters.extend(await cls._build_collaborators(pending_collaborators, workspace))
        return pending_collaborator_presenters

    @classmethod
    async def _build_collaborators(cls, collaborators: list[Collaborator], workspace: Workspace):
        results: list[CollaboratorPresenter] = []
        for collaborator in collaborators:
            results.append(CollaboratorPresenter(model=collaborator, workspace=workspace, resource=workspace.resource))

        return results

    @property
    def user_ids(self):
        return [c.model.user_id for c in self]
