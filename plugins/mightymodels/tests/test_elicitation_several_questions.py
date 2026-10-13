import asyncio
from typing import TYPE_CHECKING

from mcp.types import ElicitResult
from mightymodels_plugin.tools.tests.scripted_host import (
    SLUG,
    TICKET_INTERVIEW,
    Replies,
    exchange_with,
    review_runs,
    said,
    ticket_handoff,
    unanswered,
)
from mightymodels_plugin.tools.tests.support import StateServer

if TYPE_CHECKING:
    from mightymodels_plugin.tools.tests.scripted_host import Arguments


class TestSeveralQuestionsInOneCall:
    def test_a_review_started_with_nothing_asks_for_scope_depth_and_emphasis_together(
        self, state_server: StateServer
    ) -> None:
        arguments: Arguments = {'action': 'start'}
        replies = Replies(
            fallback=ElicitResult(action='accept', content={'choice': 'deep'}),
            by_resolver={
                'ask_scope': ElicitResult(action='accept', content={'choice': 'codebase'}),
                'ask_emphasis': ElicitResult(action='accept', content={'choice': 'balanced'}),
            },
        )

        done = asyncio.run(exchange_with(state_server, 'review', arguments, review_runs, replies))

        assert sorted(question.message for question in done.questions()) == [
            'How deep should the review go?',
            'What should the review cover?',
            'What should the review emphasize?',
        ]
        assert done.between == []
        assert done.after == [('codebase', 'deep', 'balanced')]

    def test_a_review_nobody_answers_names_every_missing_question(
        self, state_server: StateServer
    ) -> None:
        arguments: Arguments = {'action': 'start', 'payload': {'scope': 'codebase'}}

        done = asyncio.run(
            exchange_with(state_server, 'review', arguments, review_runs, unanswered('cancel'))
        )

        text = said(done.result())
        assert 'How deep should the review go?' in text
        assert 'What should the review emphasize?' in text
        assert 'What should the review cover?' not in text
        assert done.after == []

    def test_a_ticket_written_with_no_choice_asks_for_all_three(
        self, state_server: StateServer
    ) -> None:
        arguments: Arguments = {'action': 'write', 'slug': SLUG, 'fields': TICKET_INTERVIEW}
        replies = Replies(
            fallback=ElicitResult(action='accept', content={'choice': 'sm'}),
            by_resolver={
                'ask_compaction': ElicitResult(action='accept', content={'choice': True}),
                'ask_branch': ElicitResult(
                    action='accept', content={'choice': 'new', 'name': 'fix/drain'}
                ),
            },
        )

        done = asyncio.run(
            exchange_with(state_server, 'ticket', arguments, ticket_handoff, replies)
        )

        assert len(done.questions()) == 3
        assert done.between == []
        assert done.after == [
            ('scope', '"sm"'),
            ('plan-first', 'true'),
            ('branch-name', '"fix/drain"'),
        ]
