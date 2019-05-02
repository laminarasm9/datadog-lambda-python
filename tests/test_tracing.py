import unittest
try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

from datadog_lambda.constants import (
    SamplingPriority,
    TraceHeader,
    XraySubsegment,
)
from datadog_lambda.tracing import (
    extract_dd_trace_context,
    get_dd_trace_context,
    _convert_xray_trace_id,
    _convert_xray_entity_id,
    _convert_xray_sampling,
)


class TestExtractAndGetDDTraceContext(unittest.TestCase):

    def setUp(self):
        patcher = patch('datadog_lambda.tracing.xray_recorder')
        self.mock_xray_recorder = patcher.start()
        self.mock_xray_recorder.get_trace_entity.return_value = MagicMock(
            id='ffff',
            trace_id='1111',
            sampled=True,
        )
        self.mock_current_subsegment = MagicMock()
        self.mock_xray_recorder.current_subsegment.return_value = \
            self.mock_current_subsegment
        self.addCleanup(patcher.stop)

    def test_without_datadog_trace_headers(self):
        extract_dd_trace_context({})
        self.assertDictEqual(
            get_dd_trace_context(),
            {
                TraceHeader.TRACE_ID: '4369',
                TraceHeader.PARENT_ID: '65535',
                TraceHeader.SAMPLING_PRIORITY: '2',
            }
        )

    def test_with_incomplete_datadog_trace_headers(self):
        extract_dd_trace_context({
            'headers': {
                TraceHeader.TRACE_ID: '123',
                TraceHeader.PARENT_ID: '321',
            }
        })
        self.assertDictEqual(
            get_dd_trace_context(),
            {
                TraceHeader.TRACE_ID: '4369',
                TraceHeader.PARENT_ID: '65535',
                TraceHeader.SAMPLING_PRIORITY: '2',
            }
        )

    def test_with_complete_datadog_trace_headers(self):
        extract_dd_trace_context({
            'headers': {
                TraceHeader.TRACE_ID: '123',
                TraceHeader.PARENT_ID: '321',
                TraceHeader.SAMPLING_PRIORITY: '1',
            }
        })
        self.assertDictEqual(
            get_dd_trace_context(),
            {
                TraceHeader.TRACE_ID: '123',
                TraceHeader.PARENT_ID: '65535',
                TraceHeader.SAMPLING_PRIORITY: '1',
            }
        )
        self.mock_xray_recorder.begin_subsegment.assert_called()
        self.mock_xray_recorder.end_subsegment.assert_called()
        self.mock_current_subsegment.put_metadata.assert_called_with(
            XraySubsegment.KEY,
            {
                'trace-id': '123',
                'parent-id': '321',
                'sampling-priority': '1',
            },
            XraySubsegment.NAMESPACE
        )


class TestXRayContextConversion(unittest.TestCase):

    def test_convert_xray_trace_id(self):
        self.assertEqual(
            _convert_xray_trace_id('00000000e1be46a994272793'),
            '7043144561403045779'
        )

        self.assertEqual(
            _convert_xray_trace_id('bd862e3fe1be46a994272793'),
            '7043144561403045779'
        )

        self.assertEqual(
            _convert_xray_trace_id('ffffffffffffffffffffffff'),
            '9223372036854775807'  # 0x7FFFFFFFFFFFFFFF
        )

    def test_convert_xray_entity_id(self):
        self.assertEqual(
            _convert_xray_entity_id('53995c3f42cd8ad8'),
            '6023947403358210776'
        )

        self.assertEqual(
            _convert_xray_entity_id('1000000000000000'),
            '1152921504606846976'
        )

        self.assertEqual(
            _convert_xray_entity_id('ffffffffffffffff'),
            '18446744073709551615'
        )

    def test_convert_xray_sampling(self):
        self.assertEqual(
            _convert_xray_sampling(True),
            str(SamplingPriority.USER_KEEP)
        )

        self.assertEqual(
            _convert_xray_sampling(False),
            str(SamplingPriority.USER_REJECT)
        )
