"""The spool file a scout's stop leaves: its bytes, and what the server reads back from them."""

from mightymodels_plugin.commands.subagent_record import ScoutStop
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.tools.similarity.schema import Scout, SpooledReport


class TestSpoolFileContent:
    KEY = RepositoryKey('acme/retry-queue')
    STOP = ScoutStop(
        scout=Scout.CODE_SCOUT, target='code-scout a1b2', report='the café drain loop sleeps'
    )
    CONTENT = (
        b'{"repository_key":"acme/retry-queue","scout":"code-scout",'
        b'"target":"code-scout a1b2","report":"the caf\xc3\xa9 drain loop sleeps"}'
    )

    def test_the_document_is_compact_with_a_character_outside_ascii_as_utf8(self) -> None:
        assert self.STOP.spool_file_content(self.KEY) == self.CONTENT

    def test_the_server_reads_the_four_fields_back_equal(self) -> None:
        spooled = SpooledReport.model_validate_json(self.STOP.spool_file_content(self.KEY))

        assert (spooled.repository_key, spooled.scout, spooled.target, spooled.report) == (
            self.KEY,
            self.STOP.scout,
            self.STOP.target,
            self.STOP.report,
        )
