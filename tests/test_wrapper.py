import os
import unittest

try:
    from unittest.mock import patch, call, ANY, MagicMock
except ImportError:
    from mock import patch, call, ANY, MagicMock

from datadog_lambda.wrapper import datadog_lambda_wrapper, cold_start_request_id
from datadog_lambda.metric import lambda_metric


def get_mock_context(
    aws_request_id="request-id-1",
    memory_limit_in_mb="256",
    invoked_function_arn="arn:aws:lambda:us-west-1:123457598159:function:python-layer-test",
):
    lambda_context = MagicMock()
    lambda_context.aws_request_id = aws_request_id
    lambda_context.memory_limit_in_mb = memory_limit_in_mb
    lambda_context.invoked_function_arn = invoked_function_arn
    return lambda_context


class TestDatadogLambdaWrapper(unittest.TestCase):
    def setUp(self):
        patcher = patch("datadog_lambda.metric.lambda_stats")
        self.mock_metric_lambda_stats = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("datadog_lambda.wrapper.lambda_stats")
        self.mock_wrapper_lambda_stats = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("datadog_lambda.wrapper.lambda_metric")
        self.mock_wrapper_lambda_metric = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("datadog_lambda.wrapper.extract_dd_trace_context")
        self.mock_extract_dd_trace_context = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("datadog_lambda.wrapper.set_correlation_ids")
        self.mock_set_correlation_ids = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("datadog_lambda.wrapper.inject_correlation_ids")
        self.mock_inject_correlation_ids = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("datadog_lambda.wrapper.patch_all")
        self.mock_patch_all = patcher.start()
        self.addCleanup(patcher.stop)

    def test_datadog_lambda_wrapper(self):
        @datadog_lambda_wrapper
        def lambda_handler(event, context):
            lambda_metric("test.metric", 100)

        lambda_event = {}

        lambda_handler(lambda_event, get_mock_context())

        self.mock_metric_lambda_stats.distribution.assert_has_calls(
            [call("test.metric", 100, timestamp=None, tags=ANY)]
        )
        self.mock_wrapper_lambda_stats.flush.assert_called()
        self.mock_extract_dd_trace_context.assert_called_with(lambda_event)
        self.mock_set_correlation_ids.assert_called()
        self.mock_inject_correlation_ids.assert_not_called()
        self.mock_patch_all.assert_called()

    def test_datadog_lambda_wrapper_flush_to_log(self):
        os.environ["DD_FLUSH_TO_LOG"] = "True"

        @datadog_lambda_wrapper
        def lambda_handler(event, context):
            lambda_metric("test.metric", 100)

        lambda_event = {}
        lambda_handler(lambda_event, get_mock_context())

        self.mock_metric_lambda_stats.distribution.assert_not_called()
        self.mock_wrapper_lambda_stats.flush.assert_not_called()

        del os.environ["DD_FLUSH_TO_LOG"]

    def test_datadog_lambda_wrapper_inject_correlation_ids(self):
        os.environ["DD_LOGS_INJECTION"] = "True"

        @datadog_lambda_wrapper
        def lambda_handler(event, context):
            lambda_metric("test.metric", 100)

        lambda_event = {}
        lambda_handler(lambda_event, get_mock_context())

        self.mock_set_correlation_ids.assert_called()
        self.mock_inject_correlation_ids.assert_called()

        del os.environ["DD_LOGS_INJECTION"]

    def test_invocations_metric(self):
        @datadog_lambda_wrapper
        def lambda_handler(event, context):
            lambda_metric("test.metric", 100)

        lambda_event = {}

        lambda_handler(lambda_event, get_mock_context())

        self.mock_wrapper_lambda_metric.assert_has_calls(
            [
                call(
                    "aws.lambda.enhanced.invocations",
                    1,
                    tags=[
                        "region:us-west-1",
                        "account_id:123457598159",
                        "functionname:python-layer-test",
                        "memorysize:256",
                        "cold_start:true",
                    ],
                )
            ]
        )

    def test_errors_metric(self):
        @datadog_lambda_wrapper
        def lambda_handler(event, context):
            raise RuntimeError()

        lambda_event = {}

        with self.assertRaises(RuntimeError):
            lambda_handler(lambda_event, get_mock_context())

        self.mock_wrapper_lambda_metric.assert_has_calls(
            [
                call(
                    "aws.lambda.enhanced.invocations",
                    1,
                    tags=[
                        "region:us-west-1",
                        "account_id:123457598159",
                        "functionname:python-layer-test",
                        "memorysize:256",
                        "cold_start:true",
                    ],
                ),
                call(
                    "aws.lambda.enhanced.errors",
                    1,
                    tags=[
                        "region:us-west-1",
                        "account_id:123457598159",
                        "functionname:python-layer-test",
                        "memorysize:256",
                        "cold_start:true",
                    ],
                ),
            ]
        )

    def test_cold_start_tag(self):
        @datadog_lambda_wrapper
        def lambda_handler(event, context):
            lambda_metric("test.metric", 100)

        lambda_event = {}
        self.assertIsNone(cold_start_request_id)
        lambda_handler(lambda_event, get_mock_context())

        lambda_handler(
            lambda_event, get_mock_context(aws_request_id="second-request-id")
        )

        self.mock_wrapper_lambda_metric.assert_has_calls(
            [
                call(
                    "aws.lambda.enhanced.invocations",
                    1,
                    tags=[
                        "region:us-west-1",
                        "account_id:123457598159",
                        "functionname:python-layer-test",
                        "memorysize:256",
                        "cold_start:true",
                    ],
                ),
                call(
                    "aws.lambda.enhanced.invocations",
                    1,
                    tags=[
                        "region:us-west-1",
                        "account_id:123457598159",
                        "functionname:python-layer-test",
                        "memorysize:256",
                        "cold_start:false",
                    ],
                ),
            ]
        )
