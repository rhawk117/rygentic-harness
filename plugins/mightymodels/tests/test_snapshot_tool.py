"""The snapshot tool through a connected server: what the boundary refuses before the service."""

from mightymodels_plugin.tools.tests.support import StateServer, text_of


class TestAnUnstagedTicket:
    def test_a_path_shaped_slug_is_refused(
        self, connected_server: StateServer, tree_after_the_connect: dict[str, bytes]
    ) -> None:
        (refused,) = connected_server.call(('snapshot', {'slug': '../../etc'}))

        assert refused.is_error
        assert 'String should match pattern' in text_of(refused)
        assert connected_server.files_on_disk() == tree_after_the_connect
