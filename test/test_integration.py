""" Integration tests. """

import shutil
import subprocess
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from pkgcore.util import parserestrict

from nattka.bugzilla import BugCategory, BugInfo
from nattka.cli import main

from test import get_test_repo


class IntegrationTestCase(unittest.TestCase):
    """
    A test case for an integration test.  Combines Bugzilla support
    with a temporary clone of the repository.
    """

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        tempdir_path = Path(self.tempdir.name)
        basedir = Path(__file__).parent
        for subdir in ('conf', 'data'):
            shutil.copytree(basedir / subdir,
                            tempdir_path / subdir,
                            symlinks=True)

        self.repo = get_test_repo(tempdir_path)

        self.common_args = [
            '--portage-conf', str(tempdir_path / 'conf'),
            '--repo', self.repo.location,
        ]

        assert subprocess.Popen(['git', 'init'],
                                cwd=self.repo.location).wait() == 0
        assert subprocess.Popen(['git', 'add', '-A'],
                                cwd=self.repo.location).wait() == 0

    def tearDown(self):
        self.tempdir.cleanup()

    def get_package(self, atom):
        pkg = self.repo.match(parserestrict.parse_match(atom))
        assert len(pkg) == 1
        return pkg[0]


class IntegrationSuccessTests(IntegrationTestCase):
    """
    Tests for package list passing sanity-check.
    """

    def bug_preset(self, bugz, initial_status=None):
        """ Preset bugzilla mock. """
        bugz_inst = bugz.return_value
        bugz_inst.fetch_package_list.return_value = {
            560322: BugInfo(BugCategory.STABLEREQ,
                            'test/amd64-testing-1 amd64\r\n'
                            'test/alpha-amd64-hppa-testing-2 amd64 hppa\r\n',
                            [], [], [], initial_status),
        }
        return bugz_inst

    def post_verify(self):
        """ Verify that the original data has been restored. """
        self.assertEqual(
            self.get_package('=test/amd64-testing-1').keywords,
            ('~amd64',))
        self.assertEqual(
            self.get_package('=test/alpha-amd64-hppa-testing-2').keywords,
            ('~alpha', '~amd64', '~hppa'))

    @patch('nattka.cli.NattkaBugzilla')
    def test_apply(self, bugz):
        bugz_inst = self.bug_preset(bugz)
        self.assertEqual(
            main(self.common_args + ['apply', '560322']),
            0)
        bugz_inst.fetch_package_list.assert_called_with([560322])

        self.assertEqual(
            self.get_package('=test/amd64-testing-1').keywords,
            ('amd64',))
        self.assertEqual(
            self.get_package('=test/alpha-amd64-hppa-testing-2').keywords,
            ('~alpha', 'amd64', 'hppa'))

    @patch('nattka.cli.NattkaBugzilla')
    def test_process_success_n(self, bugz):
        """ Test processing with -n. """
        bugz_inst = self.bug_preset(bugz)
        self.assertEqual(
            main(self.common_args + ['process-bugs', '-n', '560322']),
            0)
        bugz_inst.fetch_package_list.assert_called_with([560322])
        bugz_inst.update_status.assert_not_called()

    @patch('nattka.cli.NattkaBugzilla')
    def test_process_success(self, bugz):
        """ Test setting new success. """
        bugz_inst = self.bug_preset(bugz)
        self.assertEqual(
            main(self.common_args + ['process-bugs', '560322']),
            0)
        bugz_inst.fetch_package_list.assert_called_with([560322])
        bugz_inst.update_status.assert_called_with(560322, True, None)

    @patch('nattka.cli.NattkaBugzilla')
    def test_process_success_from_success(self, bugz):
        """
        Test non-update when bug was marked sanity-check+ already.
        """
        bugz_inst = self.bug_preset(bugz, initial_status=True)
        self.assertEqual(
            main(self.common_args + ['process-bugs', '560322']),
            0)
        bugz_inst.fetch_package_list.assert_called_with([560322])
        bugz_inst.update_status.assert_not_called()

    @patch('nattka.cli.NattkaBugzilla')
    def test_process_success_from_failure(self, bugz):
        """ Test transition from failure to success. """
        bugz_inst = self.bug_preset(bugz, initial_status=False)
        self.assertEqual(
            main(self.common_args + ['process-bugs', '560322']),
            0)
        bugz_inst.fetch_package_list.assert_called_with([560322])
        bugz_inst.update_status.assert_called_with(560322, True,
            'All sanity-check issues have been resolved')
