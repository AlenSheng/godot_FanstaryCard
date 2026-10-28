from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'client/tests'))
from run_http_boundary import evaluate_output


class BoundaryOutputTests(unittest.TestCase):
    summary = '{"suite":"http-boundary","ok":true,"failures":[]}'
    tls = '{"path":"invalid-tls","passed":true,"result":2,"bytes":0}'
    diagnostic = 'ERROR: TLS handshake error: -9984'

    def test_expected_tls_rejection_does_not_fail_successful_suite(self):
        result = evaluate_output('\n'.join([self.tls, self.summary, self.diagnostic]), 0, True)
        self.assertTrue(result['ok'])
        self.assertTrue(result['tls_rejection_verified'])

    def test_other_errors_or_unproven_rejection_fail(self):
        for extra, tls, requested, exit_code in [
            ('SCRIPT ERROR: unexpected', self.tls, True, 0),
            ('Parse Error: invalid script', self.tls, True, 0),
            ('', '', True, 0), ('', self.tls, False, 0),
            ('', self.tls.replace('true', 'false'), True, 0),
            ('', self.tls, True, 1),
        ]:
            with self.subTest(extra=extra, tls=tls, requested=requested, exit_code=exit_code):
                self.assertFalse(evaluate_output('\n'.join([tls, self.summary, self.diagnostic, extra]), exit_code, requested)['ok'])
        self.assertFalse(evaluate_output('\n'.join([self.tls, self.summary]), 0, True)['ok'])

    def test_regular_suite_requires_a_unique_successful_summary(self):
        self.assertTrue(evaluate_output(self.summary, 0, False)['ok'])
        self.assertFalse(evaluate_output(self.summary + '\n' + self.summary, 0, False)['ok'])
        self.assertFalse(evaluate_output(self.summary.replace('true', 'false'), 0, False)['ok'])


if __name__ == '__main__': unittest.main()
