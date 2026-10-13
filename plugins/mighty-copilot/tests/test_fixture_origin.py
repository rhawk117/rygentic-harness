import pytest


def package_of(value: object) -> str:
    return type(value).__module__.split('.')[0]


class TestFixtureOrigin:
    def test_a_support_fixture_taken_as_a_parameter_comes_from_the_package_mightymodels(
        self, in_memory_git: object
    ) -> None:
        assert package_of(in_memory_git) == 'mightymodels'

    def test_a_support_fixture_fetched_by_name_comes_from_the_package_mightymodels(
        self, request: pytest.FixtureRequest
    ) -> None:
        fetched = request.getfixturevalue('in_memory_git')

        assert package_of(fetched) == 'mightymodels'
