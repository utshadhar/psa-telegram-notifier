import unittest
import datetime
import json
import threading
from unittest.mock import patch, MagicMock

# Add target directory to sys.path to import notifier
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import notifier

class TestPSATelegramNotifier(unittest.TestCase):

    def test_business_date_overnight_active(self):
        """Test overnight active window (e.g., 9 AM to 1 AM next day)"""
        start = 9
        end = 1
        
        # Scenario 1: Daytime (e.g. 15:30 on 2026-06-20) -> Business date: today, Active: True
        dt = datetime.datetime(2026, 6, 20, 15, 30, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertTrue(active)
        
        # Scenario 2: After midnight, before end (e.g. 00:30 on 2026-06-21) -> Business date: yesterday (2026-06-20), Active: True
        dt = datetime.datetime(2026, 6, 21, 0, 30, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertTrue(active)

        # Scenario 2b: Boundary check (exactly 01:00:00) -> Business date: yesterday, Active: True
        dt = datetime.datetime(2026, 6, 21, 1, 0, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertTrue(active)

        # Scenario 2c: Grace period boundary (01:04:59) -> Business date: yesterday, Active: True
        dt = datetime.datetime(2026, 6, 21, 1, 4, 59)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertTrue(active)

        # Scenario 2d: Grace period exceeded (01:05:01) -> Business date: today, Active: False
        dt = datetime.datetime(2026, 6, 21, 1, 5, 1)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 21))
        self.assertFalse(active)
        
        # Scenario 3: After midnight, after end (e.g. 02:00 on 2026-06-21) -> Business date: today (2026-06-21), Active: False
        dt = datetime.datetime(2026, 6, 21, 2, 0, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 21))
        self.assertFalse(active)

        # Scenario 4: Morning before start (e.g. 08:00 on 2026-06-20) -> Business date: today, Active: False
        dt = datetime.datetime(2026, 6, 20, 8, 0, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertFalse(active)

    def test_business_date_same_day_active(self):
        """Test same day active window (e.g., 9 AM to 5 PM / 17:00)"""
        start = 9
        end = 17
        
        # Scenario 1: Inside window (e.g., 12:00) -> Business date: today, Active: True
        dt = datetime.datetime(2026, 6, 20, 12, 0, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertTrue(active)

        # Scenario 2: Outside window (e.g., 18:00) -> Business date: today, Active: False
        dt = datetime.datetime(2026, 6, 20, 18, 0, 0)
        biz_date, active = notifier.get_business_date_and_active(dt, start, end)
        self.assertEqual(biz_date, datetime.date(2026, 6, 20))
        self.assertFalse(active)

    def test_parse_psa_data_structure(self):
        """Test pending SO/CO parser, server grouping, and deduplication logic."""
        test_payload = [
            # Server S1:
            # - Pending SO (soNumber is empty/null, TransactionId exists)
            {"serverAllocation": "S1", "soNumber": None, "TransactionId": "TX_100", "coNumber": "CO_999", "pay_id": "PAY_999"},
            # - Non-pending SO (soNumber is present)
            {"serverAllocation": "S1", "soNumber": "SO_100", "TransactionId": "TX_101", "coNumber": None, "pay_id": None},
            # - Duplicate Pending SO (same TransactionId TX_100)
            {"serverAllocation": "S1", "soNumber": "", "TransactionId": "TX_100", "coNumber": None, "pay_id": None},
            # - Pending CO (coNumber is empty/null, pay_id exists)
            {"serverAllocation": "S1", "soNumber": "SO_102", "TransactionId": "TX_102", "coNumber": "", "pay_id": "PAY_100"},
            
            # Server S2:
            # - Pending SO (soNumber is whitespace)
            {"serverAllocation": "S2", "soNumber": "   ", "TransactionId": "TX_200", "coNumber": None, "pay_id": None},
            # - Pending CO (with hyphen placeholder)
            {"serverAllocation": "S2", "soNumber": "SO_201", "TransactionId": "TX_201", "coNumber": "-", "pay_id": "PAY_200"},
            # - Completed record
            {"serverAllocation": "S2", "soNumber": "SO_202", "TransactionId": "TX_202", "coNumber": "CO_202", "pay_id": "PAY_202"},

            # Missing Server (should default to "Unknown")
            {"serverAllocation": None, "soNumber": "", "TransactionId": "TX_300", "coNumber": None, "pay_id": None}
        ]

        stats = notifier.parse_psa_data(test_payload)

        # Expected counts:
        # S1:
        # - SO unique: {"TX_100"} -> count 1
        # - CO unique: {"PAY_100"} -> count 1
        self.assertEqual(stats["server_stats"]["S1"]["pending_so"], 1)
        self.assertEqual(stats["server_stats"]["S1"]["pending_co"], 1)

        # S2:
        # - SO unique: {"TX_200"} -> count 1
        # - CO unique: {"PAY_200"} -> count 1
        self.assertEqual(stats["server_stats"]["S2"]["pending_so"], 1)
        self.assertEqual(stats["server_stats"]["S2"]["pending_co"], 1)

        # Unknown:
        # - SO unique: {"TX_300"} -> count 1
        self.assertEqual(stats["server_stats"]["Unknown"]["pending_so"], 1)
        self.assertEqual(stats["server_stats"]["Unknown"]["pending_co"], 0)

        # Totals:
        # SO: S1(1) + S2(1) + Unknown(1) = 3
        # CO: S1(1) + S2(1) + Unknown(0) = 2
        self.assertEqual(stats["total_pending_so"], 3)
        self.assertEqual(stats["total_pending_co"], 2)

    def test_parse_psa_data_wrapped_dict(self):
        """Test parser handles list wrapped inside a dict."""
        wrapped_payload = {
            "resultCode": 200,
            "dataList": [
                {"serverAllocation": "ServerA", "soNumber": "", "TransactionId": "TX_A", "coNumber": "CO_A", "pay_id": "PAY_A"},
            ]
        }
        stats = notifier.parse_psa_data(wrapped_payload)
        self.assertEqual(stats["total_pending_so"], 1)
        self.assertEqual(stats["total_pending_co"], 0)

    def test_parse_psa_data_grouped_dict(self):
        """Test parser handles dictionary with separate SO and CO keys (getALLData format)."""
        grouped_payload = {
            "SO": [
                {
                    "process": "SO",
                    "soNumber": "SO100",
                    "TransactionId": "4476293500C",
                    "serverAllocation": "8"
                },
                {
                    "process": "SO",
                    "do_number": "O005356-2026-00025",
                    "TransactionId": "4476293500D",
                    "serverAllocation": "8"
                }
            ],
            "CO": [
                {
                    "process": "CO",
                    "coNumber": "-",
                    "pay_id": "PAY_X",
                    "serverAllocation": "8"
                }
            ]
        }
        stats = notifier.parse_psa_data(grouped_payload)
        # 1 pending SO (no soNumber) and 1 pending CO (with '-')
        self.assertEqual(stats["total_pending_so"], 1)
        self.assertEqual(stats["total_pending_co"], 1)

    def test_parse_corporate_psa_data(self):
        """Test corporate API payload structure (using getCorpAllData keys)."""
        corp_payload = {
            "contract": [
                {
                    "Transaction_ID": "40245583000",
                    "contractNumber": "-",
                    "serverAllocation": "14",
                    "process": "Contract"
                },
                {
                    "Transaction_ID": "40245583001",
                    "contractNumber": "ZFCO123",
                    "serverAllocation": "14",
                    "process": "Contract"
                }
            ]
        }
        stats = notifier.parse_psa_data(corp_payload)
        # 1 pending (with '-') and 1 complete (with ZFCO123)
        self.assertEqual(stats["total_pending_so"], 0)
        self.assertEqual(stats["total_pending_co"], 1)
        self.assertEqual(stats["server_stats"]["14"]["pending_co"], 1)

    def test_format_telegram_message(self):
        """Test formatting of Telegram message."""
        stats = {
            "PSA_Pending_Orders": {
                "server_stats": {
                    "S1": {"pending_so": 5, "pending_co": 3, "so_ids": ["A", "B"], "co_ids": ["C"]},
                    "S2": {"pending_so": 1, "pending_co": 0, "so_ids": ["D"], "co_ids": []}
                },
                "total_pending_so": 6,
                "total_pending_co": 3
            },
            "SmartSales_OBD": {
                "server_stats": {
                    "1": {"pending_so": 2, "pending_co": 0, "so_ids": ["123456", "123457"], "co_ids": []}
                },
                "total_pending_so": 2,
                "total_pending_co": 0
            },
            "SAP_Contract_Pending": {
                "server_stats": {
                    "14": {"pending_so": 0, "pending_co": 2, "so_ids": [], "co_ids": ["C1", "C2"]}
                },
                "total_pending_so": 0,
                "total_pending_co": 2
            }
        }
        biz_date = datetime.date(2026, 6, 20)
        config = {
            "timezone_offset_hours": 6,
            "poll_interval_minutes": 30,
            "apis": [
                {
                    "name": "PSA_Pending_Orders"
                },
                {
                    "name": "SmartSales_OBD",
                    "label_so": "OBD",
                    "default_process": "SO"
                },
                {
                    "name": "SAP_Contract_Pending",
                    "label_co": "CON",
                    "default_process": "CO"
                }
            ]
        }
        message = notifier.format_telegram_message(stats, biz_date, config)

        self.assertIn("PSA Pending Orders Summary", message)
        self.assertIn("Business Date: 2026-06-20", message)
        self.assertIn("API Date Range: 2026-06-19 to 2026-06-20", message)
        self.assertIn("Sales Orders (SO): 6", message)
        self.assertIn("Collection Orders (CO): 3", message)
        self.assertIn("S1: SO: 5 | CO: 3", message)
        self.assertIn("S2: SO: 1 | CO: 0", message)

        self.assertIn("SmartSales OBD Pending Summary", message)
        self.assertIn("• OBD: 2", message)
        self.assertIn("• 1: OBD: 2 (Plan_Id - 123456, 123457)", message)

        self.assertIn("SAP Contract Pending Summary", message)
        self.assertIn("• CON: 2", message)
        # Verify server allocation is skipped for contract
        self.assertNotIn("14: CON", message)

    @patch('urllib.request.urlopen')
    def test_send_telegram_notification(self, mock_urlopen):
        """Test sending telegram notification returns correct success status."""
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat"
        }
        
        # Mock successful send
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true, "result": {"message_id": 123}}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        success, _ = notifier.send_telegram_notification("Test Message", config)
        self.assertTrue(success)

        # Mock failed send
        mock_response.read.return_value = b'{"ok": false, "description": "Unauthorized"}'
        success, _ = notifier.send_telegram_notification("Test Message", config)
        self.assertFalse(success)

    @patch('urllib.request.urlopen')
    @patch('notifier.send_telegram_notification')
    def test_check_and_send_pending_alert(self, mock_send, mock_urlopen):
        """Test that check_and_send_pending_alert correctly calls send_telegram_notification if data is pending."""
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat",
            "psa_pending_check_url_template": "https://psa.mgi.org/api/getALLData/{business_date}/{business_date}/0?server=0"
        }
        business_date = datetime.date(2026, 7, 8)
        
        # Scenario 1: There is pending data
        pending_payload = {
            "SO": [
                {"process": "SO", "do_number": "O003120-2026-00056", "TransactionId": "622883120Z", "serverAllocation": "2", "soNumber": ""}
            ],
            "CO": []
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(pending_payload).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        notifier.check_and_send_pending_alert(business_date, config)
        
        # Verify that send_telegram_notification was called with the correct alert message
        mock_send.assert_called_with("PSA Data still pending\n(Pending SO: 1, Pending CO: 0)", config)
        mock_send.reset_mock()
        
        # Scenario 2: There is no pending data
        no_pending_payload = {
            "SO": [
                {"process": "SO", "do_number": "O003120-2026-00056", "TransactionId": "622883120Z", "serverAllocation": "2", "soNumber": "SO12345"}
            ],
            "CO": []
        }
        mock_response.read.return_value = json.dumps(no_pending_payload).encode('utf-8')
        notifier.check_and_send_pending_alert(business_date, config)
        
        # Verify send_telegram_notification was NOT called
        # Verify send_telegram_notification was NOT called
        mock_send.assert_not_called()

    def test_is_time_for_pending_alert(self):
        """Test the late-night pending check scheduler active window calculation."""
        # 1. Overnight window: 23:00 to 01:05 (end_hour=1)
        end_hour = 1
        
        # Scenario 1.1: Before 23:00 (10:59 PM) -> False
        dt_before = datetime.datetime(2026, 7, 8, 22, 59, 0)
        self.assertFalse(notifier.is_time_for_pending_alert(dt_before, end_hour))
        
        # Scenario 1.2: Exactly 23:00 (11:00 PM) -> True
        dt_start = datetime.datetime(2026, 7, 8, 23, 0, 0)
        self.assertTrue(notifier.is_time_for_pending_alert(dt_start, end_hour))
        
        # Scenario 1.3: Midnight (00:00) -> True
        dt_midnight = datetime.datetime(2026, 7, 9, 0, 0, 0)
        self.assertTrue(notifier.is_time_for_pending_alert(dt_midnight, end_hour))
        
        # Scenario 1.4: Within 5 min grace of end_hour (01:04 AM) -> True
        dt_grace = datetime.datetime(2026, 7, 9, 1, 4, 0)
        self.assertTrue(notifier.is_time_for_pending_alert(dt_grace, end_hour))
        
        # Scenario 1.5: After grace of end_hour (01:06 AM) -> False
        dt_after = datetime.datetime(2026, 7, 9, 1, 6, 0)
        self.assertFalse(notifier.is_time_for_pending_alert(dt_after, end_hour))
        
        # Scenario 1.6: Morning (09:00 AM) -> False
        dt_morning = datetime.datetime(2026, 7, 8, 9, 0, 0)
        self.assertFalse(notifier.is_time_for_pending_alert(dt_morning, end_hour))

    @patch('urllib.request.urlopen')
    @patch('notifier.send_telegram_notification')
    def test_check_and_send_pending_alert_force_logic(self, mock_send, mock_urlopen):
        """Test force logic in check_and_send_pending_alert."""
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat",
            "psa_pending_check_url_template": "https://psa.mgi.org/api/getALLData/{business_date}/{business_date}/0?server=0",
            "monitoring_start_hour": 9,
            "monitoring_end_hour": 1
        }
        business_date = datetime.date(2026, 7, 8)
        
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"SO": [], "CO": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Scenario 2.1: force=False outside hours -> does not trigger urlopen
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 5, 0, 0)):
            notifier.check_and_send_pending_alert(business_date, config, force=False)
            mock_urlopen.assert_not_called()
            
        # Scenario 2.2: force=True outside hours -> triggers urlopen
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 5, 0, 0)):
            notifier.check_and_send_pending_alert(business_date, config, force=True)
            mock_urlopen.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_fetch_and_parse_url_formatting(self, mock_urlopen):
        """Test that fetch_and_parse constructs URLs with correct yesterday/today date ranges."""
        api_config = {
            "name": "PSA",
            "url_template": "https://psa.mgi.org/api/getALLData/{date}/{date}/1,2,3?server=0",
            "filter_pending": True
        }
        
        # Mock API response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"SO": [], "CO": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Target date is June 21, 2026 (today)
        biz_date = datetime.date(2026, 6, 21)
        notifier.fetch_and_parse(biz_date, api_config)

        # Expected start_date (yesterday) = 2026-06-20
        # Expected end_date (today) = 2026-06-21
        expected_url = "https://psa.mgi.org/api/getALLData/2026-06-20/2026-06-21/1,2,3?server=0"
        
        # Verify the urlopen was called with the correctly formatted request url
        called_args = mock_urlopen.call_args[0]
        req = called_args[0]
        self.assertEqual(req.full_url, expected_url)

        # Also test with new placeholder style
        api_config_new = {
            "name": "PSA",
            "url_template": "https://psa.mgi.org/api/getALLData/{start_date}/{end_date}/1,2,3?server=0",
            "filter_pending": True
        }
        mock_urlopen.reset_mock()
        notifier.fetch_and_parse(biz_date, api_config_new)
        called_args_new = mock_urlopen.call_args[0]
        req_new = called_args_new[0]
        self.assertEqual(req_new.full_url, expected_url)

    def test_parse_psa_data_no_filtering(self):
        """Test parse_psa_data with filter_pending=False (count all returned items as pending)."""
        test_payload = {
            "SO": [
                # Standard SO with a sales order number (normally ignored, but should be counted)
                {"serverAllocation": "S1", "soNumber": "SO_100", "TransactionId": "TX_100", "coNumber": None, "pay_id": None}
            ],
            "CO": [
                # Standard CO with a contract number (normally ignored, but should be counted)
                {"serverAllocation": "S1", "soNumber": None, "TransactionId": "TX_101", "coNumber": "CO_100", "pay_id": "PAY_100"}
            ]
        }
        stats = notifier.parse_psa_data(test_payload, filter_pending=False)
        self.assertEqual(stats["total_pending_so"], 1)
        self.assertEqual(stats["total_pending_co"], 1)

    @patch('urllib.request.urlopen')
    def test_fetch_all_apis_aggregation(self, mock_urlopen):
        """Test that fetch_all_apis aggregates statistics from multiple API sources."""
        config = {
            "apis": [
                {
                    "name": "PSA",
                    "url_template": "https://psa.mgi.org/api/getALLData/{date}/{date}/1,2,3?server=0",
                    "filter_pending": True
                },
                {
                    "name": "API_2",
                    "url_template": "https://psa.mgi.org/api/getALLData2/{date}/{date}/1,2,3?server=0",
                    "filter_pending": False
                }
            ]
        }
        
        # Mock responses for the two APIs:
        # API 1 (PSA, filtered): Returns 1 completed SO and 1 pending SO. Only the pending should be counted.
        # API 2 (API_2, unfiltered): Returns 1 completed SO. Since filter_pending is False, it should be counted.
        mock_response_1 = MagicMock()
        mock_response_1.read.return_value = b'{"SO": [{"serverAllocation": "S1", "soNumber": "SO_10", "TransactionId": "TX_1"}, {"serverAllocation": "S1", "soNumber": "", "TransactionId": "TX_2"}]}'
        
        mock_response_2 = MagicMock()
        mock_response_2.read.return_value = b'{"SO": [{"serverAllocation": "S1", "soNumber": "SO_20", "TransactionId": "TX_3"}]}'
        
        # We make urlopen return these mock responses deterministically based on request URL
        def mock_urlopen_fn(req, *args, **kwargs):
            url = req.full_url if hasattr(req, 'full_url') else req
            mock_res = MagicMock()
            if "getALLData2" in url:
                mock_res.read.return_value = b'{"SO": [{"serverAllocation": "S1", "soNumber": "SO_20", "TransactionId": "TX_3"}]}'
            else:
                mock_res.read.return_value = b'{"SO": [{"serverAllocation": "S1", "soNumber": "SO_10", "TransactionId": "TX_1"}, {"serverAllocation": "S1", "soNumber": "", "TransactionId": "TX_2"}]}'
            return MagicMock(__enter__=MagicMock(return_value=mock_res))
            
        mock_urlopen.side_effect = mock_urlopen_fn

        biz_date = datetime.date(2026, 6, 21)
        stats = notifier.fetch_all_apis(biz_date, config)

        # Expected counts:
        # API 1 pending SO: TX_2 (count 1)
        # API 2 pending SO: TX_3 (count 1 because filter_pending is False)
        self.assertIn("PSA", stats)
        self.assertIn("API_2", stats)
        self.assertEqual(stats["PSA"]["total_pending_so"], 1)
        self.assertEqual(stats["API_2"]["total_pending_so"], 1)
        self.assertEqual(stats["PSA"]["server_stats"]["S1"]["pending_so"], 1)
        self.assertEqual(stats["API_2"]["server_stats"]["S1"]["pending_so"], 1)

    @patch('urllib.request.urlopen')
    def test_fetch_and_parse_custom_headers(self, mock_urlopen):
        """Test that fetch_and_parse injects custom headers into the urllib request."""
        api_config = {
            "name": "Cement_SO_Collection",
            "url_template": "https://smartsales.mgi.org/api/get-so-payment-collection?start={date}",
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer TEST_TOKEN"
            }
        }
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"SO": [], "CO": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        biz_date = datetime.date(2026, 6, 21)
        notifier.fetch_and_parse(biz_date, api_config)

        # Inspect request
        called_args = mock_urlopen.call_args[0]
        req = called_args[0]
        self.assertEqual(req.headers.get("Accept"), "application/json")
        self.assertEqual(req.headers.get("Authorization"), "Bearer TEST_TOKEN")

    def test_parse_psa_data_custom_keys(self):
        """Test parse_psa_data parses Transactionid, Payid, and plan_id unique keys correctly."""
        test_payload = {
            "SO": [
                # Pending SO with lowercase Transactionid
                {"serverAllocation": "S1", "soNumber": None, "Transactionid": "TX_100"},
                # Pending SO with plan_id
                {"serverAllocation": "S1", "soNumber": None, "plan_id": "PLAN_200"}
            ],
            "CO": [
                # Pending CO with Payid
                {"serverAllocation": "S2", "coNumber": None, "Payid": "PAY_300"}
            ]
        }
        stats = notifier.parse_psa_data(test_payload)
        self.assertEqual(stats["server_stats"]["S1"]["pending_so"], 2)
        self.assertEqual(stats["server_stats"]["S2"]["pending_co"], 1)

    def test_parse_psa_data_default_process(self):
        """Test parse_psa_data properly forces classifications based on default_process override."""
        test_payload_so = [
            # Flat list with plan_id
            {"serverAllocation": "S1", "plan_id": "PLAN_A"},
            {"serverAllocation": "S1", "plan_id": "PLAN_B"}
        ]
        
        # When default_process="SO"
        stats_so = notifier.parse_psa_data(test_payload_so, filter_pending=False, default_process="SO")
        self.assertEqual(stats_so["total_pending_so"], 2)
        self.assertEqual(stats_so["total_pending_co"], 0)

        test_payload_co = [
            # Flat list with TransactionId
            {"serverAllocation": "S1", "TransactionId": "TX_A"},
            {"serverAllocation": "S1", "TransactionId": "TX_B"}
        ]

        # When default_process="CO"
        stats_co = notifier.parse_psa_data(test_payload_co, filter_pending=False, default_process="CO")
        self.assertEqual(stats_co["total_pending_so"], 0)
        self.assertEqual(stats_co["total_pending_co"], 2)

    def test_user_provided_examples(self):
        """Test parsing of user-provided example payloads for SmartSales, OBD, and SAP Contract."""
        # 1. SmartSales SO/CO
        smartsales_payload = {
            "SO": [
                {"process": "SO", "do_number": "O003120-2026-00056", "TransactionId": "622883120Z", "serverAllocation": "2"},
                {"process": "SO", "do_number": "O003120-2026-00057", "TransactionId": "622913120Z", "serverAllocation": "3"},
                {"process": "SO", "do_number": "O003120-2026-00056", "TransactionId": "622883120Z", "serverAllocation": "2"},
                {"process": "SO", "do_number": "O003120-2026-00056", "TransactionId": "622883120Z", "serverAllocation": "2"},
                {"process": "SO", "do_number": "O003120-2026-00057", "TransactionId": "622913120Z", "serverAllocation": "3"},
                {"process": "SO", "do_number": "O003120-2026-00057", "TransactionId": "622913120Z", "serverAllocation": "3"}
            ],
            "CO": [
                {"process": "CO", "pay_id": 44620, "TransactionId": "4462011031", "serverAllocation": "4"},
                {"process": "CO", "pay_id": 44618, "TransactionId": "4461811031", "serverAllocation": "3"},
                {"process": "CO", "pay_id": 44665, "orderNumber": "O003120-2026-00056", "TransactionId": "4466514323", "serverAllocation": "2"}
            ]
        }
        stats_ss = notifier.parse_psa_data(smartsales_payload, filter_pending=False)
        self.assertEqual(stats_ss["total_pending_so"], 2)
        self.assertEqual(stats_ss["total_pending_co"], 3)
        self.assertEqual(stats_ss["server_stats"]["2"]["pending_so"], 1)
        self.assertEqual(stats_ss["server_stats"]["2"]["pending_co"], 1)
        self.assertEqual(stats_ss["server_stats"]["3"]["pending_so"], 1)
        self.assertEqual(stats_ss["server_stats"]["3"]["pending_co"], 1)
        self.assertEqual(stats_ss["server_stats"]["4"]["pending_co"], 1)

        # 2. Cement OBD Program (dynamic keys, Plan_Id, Server_Allocation)
        obd_payload = {
            "EXW_EWV": [
                {"Plan_Id": 405708, "Server_Allocation": 1},
                {"Plan_Id": 405708, "Server_Allocation": 1},
                {"Plan_Id": 405710, "Server_Allocation": 2},
                {"Plan_Id": 405710, "Server_Allocation": 2},
                {"Plan_Id": 405712, "Server_Allocation": 1},
                {"Plan_Id": 405712, "Server_Allocation": 1}
            ],
            "CFR_CFV": [
                {"Plan_Id": 405660, "Server_Allocation": 2},
                {"Plan_Id": 405660, "Server_Allocation": 2},
                {"Plan_Id": 405674, "Server_Allocation": 2},
                {"Plan_Id": 405674, "Server_Allocation": 2}
            ]
        }
        stats_obd = notifier.parse_psa_data(obd_payload, filter_pending=False, default_process="SO")
        self.assertEqual(stats_obd["total_pending_so"], 5)
        self.assertEqual(stats_obd["total_pending_co"], 0)
        self.assertEqual(stats_obd["server_stats"]["1"]["pending_so"], 2)
        self.assertEqual(stats_obd["server_stats"]["2"]["pending_so"], 3)

        # 3. SAP Contract Create (Transaction_ID, serverAllocation)
        sap_payload = {
            "contract": [
                {"process": "Contract", "Transaction_ID": "3614293280C", "contractNumber": "", "serverAllocation": "14"},
                {"process": "Contract", "Transaction_ID": "3614293270C", "contractNumber": "", "serverAllocation": "15"}
            ]
        }
        stats_sap = notifier.parse_psa_data(sap_payload, filter_pending=False, default_process="CO")
        self.assertEqual(stats_sap["total_pending_so"], 0)
        self.assertEqual(stats_sap["total_pending_co"], 2)
        self.assertEqual(stats_sap["server_stats"]["14"]["pending_co"], 1)
        self.assertEqual(stats_sap["server_stats"]["15"]["pending_co"], 1)

    def test_cv_sorting_parsing(self):
        """Test parsing of the CV Sorting API responses."""
        from unittest.mock import patch, MagicMock
        import io
        
        cv_payload = {
            "status": "success",
            "data": [
                {"task_no": "TASK1", "status": "pending"},
                {"task_no": "TASK2", "status": "pending"},
                {"task_no": "TASK3", "status": "downloading"},
                {"task_no": "TASK4", "status": "downloaded"},
                {"task_no": "TASK5", "status": "notfound"},
                {"task_no": "TASK6", "status": "screening"},
                {"task_no": "TASK7", "status": "completed"}  # Should be ignored
            ]
        }
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(cv_payload).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        
        config = {
            "cv_sorting_api_url": "http://mock-intranet/cv-api",
            "cv_sorting_api_cookie": "sess_id=123"
        }
        
        with patch('urllib.request.urlopen', return_value=mock_response) as mock_urlopen:
            stats = notifier.fetch_cv_sorting_data(config)
            
            # Verify request headers
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.get_header("Cookie"), "sess_id=123")
            
            self.assertEqual(stats["pending"], ["Task1", "Task2"])
            self.assertEqual(stats["downloading"], ["Task3"])
            self.assertEqual(stats["downloaded"], ["Task4"])
            self.assertEqual(stats["notfound"], ["Task5"])
            self.assertEqual(stats["screening"], ["Task6"])

    def test_rpa_config_parsing(self):
        """Test parsing of the RPA Config API responses."""
        from unittest.mock import patch, MagicMock
        
        rpa_payload = {
            "LIVEDATA": "ON",
            "PROFILECOUNT": "8"
        }
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(rpa_payload).encode('utf-8')
        mock_response.__enter__.return_value = mock_response
        
        config = {
            "rpa_config_api_url": "http://mock-intranet/rpa-api"
        }
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            res = notifier.fetch_rpa_config_data(config)
            self.assertEqual(res["profile_count"], "8")

    def test_cv_sorting_and_rpa_formatting(self):
        """Test formatting of the CV Sorting and RPA statistics inside the Telegram message."""
        stats = {
            "_cv_sorting": {
                "pending": ["Task1", "Task2"],
                "downloading": ["Task3"],
                "downloaded": ["Task4"],
                "notfound": ["Task5"],
                "screening": ["Task6"]
            },
            "_rpa_config": {
                "profile_count": "15"
            }
        }
        
        config = {
            "timezone_offset_hours": 6,
            "poll_interval_minutes": 30,
            "cv_sorting_api_url": "http://mock-intranet/cv-api",
            "rpa_config_api_url": "http://mock-intranet/rpa-api",
            "apis": []
        }
        
        business_date = datetime.date(2026, 6, 24)
        msg = notifier.format_telegram_message(stats, business_date, config)
        
        # Verify the message contains all custom output fields
        self.assertIn("CV Sorting -", msg)
        self.assertIn("Pending - 2 (Task1, Task2)", msg)
        self.assertIn("Downloading - 1 (Task3)", msg)
        self.assertIn("Downloaded - 1 (Task4)", msg)
        self.assertIn("Not Found - 1 (Task5)", msg)
        self.assertIn("Screening - 1 (Task6)", msg)
        self.assertIn("Profile Count - 15", msg)

    @patch('notifier.send_telegram_notification')
    def test_aging_alert_checking(self, mock_send):
        """Test that track_and_alert_aging dispatches alerts when threshold is crossed."""
        config = {
            "timezone_offset_hours": 6
        }
        
        notifier.PENDING_FIRST_SEEN = {}
        notifier.PENDING_ALERTS_SENT = {}
        notifier.PSA_SO_PENDING_THRESHOLD_MINUTES = 2
        
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 10, 0, 0)):
            notifier.track_and_alert_aging("TX_1", "S1", "SO", "PSA", config)
            mock_send.assert_not_called()
            
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 10, 1, 0)):
            notifier.track_and_alert_aging("TX_1", "S1", "SO", "PSA", config)
            mock_send.assert_not_called()
            
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 10, 3, 0)):
            notifier.track_and_alert_aging("TX_1", "S1", "SO", "PSA", config)
            mock_send.assert_called_once_with("PSA SO TransactionId is TX_1 in server S1 for 3 min 0 sec", config)
            
        mock_send.reset_mock()
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 10, 4, 0)):
            notifier.track_and_alert_aging("TX_1", "S1", "SO", "PSA", config)
            mock_send.assert_not_called()
            
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 10, 14, 0)):
            notifier.track_and_alert_aging("TX_1", "S1", "SO", "PSA", config)
            mock_send.assert_not_called()
            
        with patch('notifier.get_local_time', return_value=datetime.datetime(2026, 7, 8, 10, 17, 0)):
            notifier.track_and_alert_aging("TX_1", "S1", "SO", "PSA", config)
            mock_send.assert_called_once_with("PSA SO TransactionId is TX_1 in server S1 for 3 min 0 sec", config)
            
        notifier.parse_psa_data({"SO": []}, filter_pending=True, api_name="PSA", config=config)
        self.assertNotIn(("SO", "PSA", "TX_1"), notifier.PENDING_FIRST_SEEN)

    def test_webhook_conversational_flow(self):
        """Test conversational state handling in the webhook POST handler using callback queries and inline keyboards."""
        class MockRequestHandler(notifier.RequestHandler):
            def __init__(self):
                self.headers = {}
                self.rfile = None
                self.path = '/webhook'
                self.response_code = None
                self.response_body = None
                
            def send_json_response(self, code, body):
                self.response_code = code
                self.response_body = body
                
        with patch('notifier.load_config', return_value={"telegram_chat_id": "123"}), \
             patch('notifier.send_telegram_notification') as mock_send, \
             patch('notifier.telegram_api_call') as mock_api:
             
            handler = MockRequestHandler()
            
            def simulate_webhook_msg(text):
                import io
                payload = {
                    "message": {
                        "chat": {"id": 123},
                        "text": text
                    }
                }
                body_bytes = json.dumps(payload).encode('utf-8')
                handler.headers = {'Content-Length': str(len(body_bytes))}
                handler.rfile = io.BytesIO(body_bytes)
                handler.do_POST()
                        # 1. Trigger f1 -> Bot should set state to AWAITING_VAL_F1
            notifier.USER_CONVERSATION_STATE = None
            simulate_webhook_msg("f1")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, "AWAITING_VAL_F1")
            mock_send.assert_called_once()
            self.assertIn("psa_so_pending_threshold_minutes", mock_send.call_args[0][0])
            mock_send.reset_mock()
 
            # 2. User replies with text "23" -> updates PSA_SO_PENDING_THRESHOLD_MINUTES and _DEFAULT to 23
            simulate_webhook_msg("23")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, None)
            self.assertEqual(notifier.PSA_SO_PENDING_THRESHOLD_MINUTES, 23)
            self.assertEqual(notifier.PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, 23)
            mock_send.assert_called_with("psa_so_pending_threshold_minutes set to 23 min.", {"telegram_chat_id": "123"})
            mock_send.reset_mock()
 
            # 3. Turn off f1 directly via shortcut
            simulate_webhook_msg("o1")
            self.assertEqual(notifier.PSA_SO_PENDING_THRESHOLD_MINUTES, 0)
            self.assertEqual(notifier.PSA_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, 0)
            mock_send.assert_called_with("psa_so_pending_threshold_minutes checker is off.", {"telegram_chat_id": "123"})
            mock_send.reset_mock()
 
            # 4. Trigger f6
            simulate_webhook_msg("f6")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, "AWAITING_VAL_F6")
            mock_send.assert_called_once()
            self.assertIn("SAP_Contract_pending_threshold_minutes", mock_send.call_args[0][0])
            mock_send.reset_mock()
 
            # 5. User replies with text "7 min" -> updates CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES to 7
            simulate_webhook_msg("7 min")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, None)
            self.assertEqual(notifier.CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES, 7)
            self.assertEqual(notifier.CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, 7)
            mock_send.assert_called_with("SAP_Contract_pending_threshold_minutes set to 7 min.", {"telegram_chat_id": "123"})
            mock_send.reset_mock()
 
            # 6. Turn off f6 directly
            simulate_webhook_msg("f6 off")
            self.assertEqual(notifier.CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES, 0)
            self.assertEqual(notifier.CONTRACTAPI_CO_PENDING_THRESHOLD_MINUTES_DEFAULT, 0)
            mock_send.assert_called_with("SAP_Contract_pending_threshold_minutes checker is off.", {"telegram_chat_id": "123"})
            mock_send.reset_mock()
            
            # 7. Trigger f3 and then interrupt with f4
            simulate_webhook_msg("f3")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, "AWAITING_VAL_F3")
            mock_send.reset_mock()
            
            simulate_webhook_msg("/f4")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, "AWAITING_VAL_F4")
            mock_send.assert_called_once()
            self.assertIn("Smartsales_so_pending_threshold_minutes", mock_send.call_args[0][0])
            mock_send.reset_mock()
 
            simulate_webhook_msg("15")
            self.assertEqual(notifier.USER_CONVERSATION_STATE, None)
            mock_send.reset_mock()
 
            simulate_webhook_msg("feature")
            mock_send.assert_called_once()
            feature_msg = mock_send.call_args[0][0]
            self.assertIn("variable name - f1", feature_msg)
            self.assertIn("default value -", feature_msg)
            self.assertIn("current value -", feature_msg)
            self.assertIn("description -", feature_msg)

    @patch('notifier.fetch_all_apis')
    @patch('notifier.check_and_send_pending_alert')
    @patch('notifier.load_config')
    @patch('notifier.get_local_time')
    @patch('notifier.get_business_date_and_active')
    def test_aging_alerts_scheduler_loop(self, mock_active, mock_get_time, mock_load, mock_check, mock_fetch):
        """Test the aging alerts background scheduler loop execution conditions."""
        notifier.PSA_SO_PENDING_THRESHOLD_MINUTES = 10
        
        stop_event = threading.Event()
        stop_event.set()
        
        notifier.aging_alerts_scheduler_loop(stop_event)
        mock_fetch.assert_not_called()
        
        stop_event = threading.Event()
        mock_load.return_value = {"monitoring_start_hour": 9, "monitoring_end_hour": 1}
        mock_get_time.return_value = datetime.datetime(2026, 7, 8, 10, 0, 0)
        mock_active.return_value = (datetime.date(2026, 7, 8), True)
        
        def side_effect(timeout):
            stop_event.set()
            return False
        stop_event.wait = side_effect
        
        notifier.aging_alerts_scheduler_loop(stop_event)
        mock_fetch.assert_called_once()
        mock_check.assert_not_called()

    def test_clear_aging_memory(self):
        """Test that clear_aging_memory correctly wipes tracking state for a specific process type."""
        notifier.PENDING_FIRST_SEEN = {
            ("SO", "PSA", "TX_SO"): datetime.datetime.now(),
            ("CO", "PSA", "TX_CO"): datetime.datetime.now()
        }
        notifier.PENDING_ALERTS_SENT = {
            ("SO", "PSA", "TX_SO", 2): datetime.datetime.now(),
            ("CO", "PSA", "TX_CO", 2): datetime.datetime.now()
        }
        
        notifier.clear_aging_memory("SO")
        
        self.assertNotIn(("SO", "PSA", "TX_SO"), notifier.PENDING_FIRST_SEEN)
        self.assertIn(("CO", "PSA", "TX_CO"), notifier.PENDING_FIRST_SEEN)
        self.assertNotIn(("SO", "PSA", "TX_SO", 2), notifier.PENDING_ALERTS_SENT)
        self.assertIn(("CO", "PSA", "TX_CO", 2), notifier.PENDING_ALERTS_SENT)

    def test_thresholds_persistence(self):
        """Test that thresholds can be saved to config.json and loaded back."""
        import tempfile
        temp_dir = tempfile.mkdtemp()
        temp_config_path = os.path.join(temp_dir, "config.json")
        
        # Write empty config
        with open(temp_config_path, "w") as f:
            json.dump({}, f)
            
        with patch("notifier.CONFIG_PATH", temp_config_path):
            # 1. Store old settings
            old_val = notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES
            old_def = notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT
            
            # 2. Modify value
            notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = 42
            notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES = 42
            notifier.save_thresholds()
            
            # 3. Reset in-memory to default/other value
            notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = 15
            notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES = 15
            
            # 4. Load from file and assert
            notifier.load_thresholds()
            self.assertEqual(notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT, 42)
            self.assertEqual(notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES, 42)
            
            # Restore
            notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES = old_val
            notifier.CEMENTAPI_SO_PENDING_THRESHOLD_MINUTES_DEFAULT = old_def
            
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception:
            pass

    def test_is_hour_in_range(self):
        """Test that is_hour_in_range correctly handles normal and wrap-around windows."""
        # Same day: 9 AM to 5 PM
        self.assertTrue(notifier.is_hour_in_range(12, 9, 17))
        self.assertTrue(notifier.is_hour_in_range(9, 9, 17))
        self.assertFalse(notifier.is_hour_in_range(17, 9, 17))
        self.assertFalse(notifier.is_hour_in_range(8, 9, 17))

        # Overnight wrap-around: 1 AM to 8 AM
        self.assertTrue(notifier.is_hour_in_range(1, 1, 8))
        self.assertTrue(notifier.is_hour_in_range(4, 1, 8))
        self.assertTrue(notifier.is_hour_in_range(7, 1, 8))
        self.assertFalse(notifier.is_hour_in_range(8, 1, 8))
        self.assertFalse(notifier.is_hour_in_range(0, 1, 8))
        self.assertFalse(notifier.is_hour_in_range(12, 1, 8))

        # Wrap-around midnight: 10 PM to 6 AM (22 to 6)
        self.assertTrue(notifier.is_hour_in_range(23, 22, 6))
        self.assertTrue(notifier.is_hour_in_range(1, 22, 6))
        self.assertFalse(notifier.is_hour_in_range(12, 22, 6))

    def test_f7_offhours_alerts(self):
        """Test that track_and_alert_aging behaves correctly in and out of the f7 off-hours window."""
        notifier.PENDING_FIRST_SEEN = {}
        notifier.PENDING_ALERTS_SENT = {}
        
        # Enable off-hours OBD checker f7 (default 30 min, hours 1 to 8)
        notifier.SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES = 30
        notifier.OBD_OFFHOURS_START_HOUR = 1
        notifier.OBD_OFFHOURS_END_HOUR = 8
        notifier.OBD_PENDING_THRESHOLD_MINUTES = 20
        
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat",
            "monitoring_start_hour": 9,
            "monitoring_end_hour": 1
        }
        
        # Mock send_telegram_notification
        with patch("notifier.send_telegram_notification") as mock_send:
            mock_send.return_value = (True, None)
            
            # Scenario 1: Local time is 3 AM (inside f7 window, outside regular monitoring hours)
            # Since we are outside active business hours (which are 9 AM to 1 AM), f7 OBD alerts should trigger after 30 min
            # A pending transaction first seen at 2:25 AM (35 mins old) should trigger alert.
            with patch("notifier.get_local_time") as mock_time:
                mock_time.return_value = datetime.datetime(2026, 6, 20, 3, 0, 0)
                
                # Check normal SO alert (non-OBD) at 3 AM -> should return early (regular checker inactive)
                notifier.track_and_alert_aging("TX_SO", "Server1", "SO", "PSA", config)
                self.assertNotIn(("SO", "PSA", "TX_SO"), notifier.PENDING_FIRST_SEEN)
                
                # Check OBD alert at 3 AM:
                # First seen at 3 AM
                notifier.track_and_alert_aging("TX_OBD", "Server1", "OBD", "API_3", config)
                self.assertIn(("OBD", "API_3", "TX_OBD"), notifier.PENDING_FIRST_SEEN)
                
                # Age is 35 mins old (mock time is 3:35 AM)
                mock_time.return_value = datetime.datetime(2026, 6, 20, 3, 35, 0)
                notifier.track_and_alert_aging("TX_OBD", "Server1", "OBD", "API_3", config)
                mock_send.assert_called_once()
                self.assertIn(("OBD", "API_3", "TX_OBD", 30), notifier.PENDING_ALERTS_SENT)

    def test_callmebot_trigger_and_alert(self):
        """Test that track_and_alert_aging initiates a CallMeBot call during off-hours OBD alert triggers."""
        notifier.PENDING_FIRST_SEEN = {}
        notifier.PENDING_ALERTS_SENT = {}
        
        notifier.SMARTSALES_OBD_OFFHOURS_THRESHOLD_MINUTES = 30
        notifier.OBD_OFFHOURS_START_HOUR = 1
        notifier.OBD_OFFHOURS_END_HOUR = 8
        notifier.CALLMEBOT_USER = "UshDhar, +8801838262248"
        
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat",
            "monitoring_start_hour": 9,
            "monitoring_end_hour": 1
        }
        
        with patch("notifier.send_telegram_notification") as mock_send, \
             patch("notifier.trigger_callmebot_call_async") as mock_call, \
             patch("notifier.get_local_time") as mock_time:
            mock_send.return_value = (True, None)
            
            # Local time is 3 AM (inside f7 window)
            mock_time.return_value = datetime.datetime(2026, 6, 20, 3, 0, 0)
            
            # First check -> registered in memory
            notifier.track_and_alert_aging("TX_OBD", "Server1", "OBD", "API_3", config)
            
            # Age is 35 mins old
            mock_time.return_value = datetime.datetime(2026, 6, 20, 3, 35, 0)
            notifier.track_and_alert_aging("TX_OBD", "Server1", "OBD", "API_3", config)
            
            # Verify both telegram text message and voice call helper were triggered!
            mock_send.assert_called_once()
            mock_call.assert_called_once_with("SmartSales OBD Plan_Id is TX_OBD in server Server1 for 35 min 0 sec", config)

    def test_freshlpg_thresholds(self):
        """Test FreshLPG thresholds, status, and config loading logic."""
        # 1. Defaults check
        notifier.load_thresholds()
        self.assertEqual(notifier.FRESHLPG_SO_PENDING_THRESHOLD_MINUTES, 15)
        self.assertEqual(notifier.FRESHLPG_CO_PENDING_THRESHOLD_MINUTES, 10)

        # 2. track_and_alert_aging mapping for FreshLPG
        notifier.PENDING_FIRST_SEEN = {}
        notifier.PENDING_ALERTS_SENT = {}
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat",
            "monitoring_start_hour": 9,
            "monitoring_end_hour": 1
        }
        with patch("notifier.send_telegram_notification") as mock_send, \
             patch("notifier.get_local_time") as mock_time:
            mock_send.return_value = (True, None)
            
            # Active monitoring time (10 AM)
            mock_time.return_value = datetime.datetime(2026, 6, 20, 10, 0, 0)
            
            # First check for SO -> registered
            notifier.track_and_alert_aging("TX_SO", "Server1", "SO", "API_5", config)
            self.assertIn(("SO", "API_5", "TX_SO"), notifier.PENDING_FIRST_SEEN)
            
            # Time passes by 16 minutes (exceeds SO threshold of 15)
            mock_time.return_value = datetime.datetime(2026, 6, 20, 10, 16, 0)
            notifier.track_and_alert_aging("TX_SO", "Server1", "SO", "API_5", config)
            mock_send.assert_called_once()
            self.assertIn(("SO", "API_5", "TX_SO", 15), notifier.PENDING_ALERTS_SENT)

    def test_state_switcher_and_aliases(self):
        """Test state switcher commands (/switch_to_render, /switch_to_local) and short off-aliases (/o1-/o9)."""
        config = {
            "telegram_bot_token": "mock_token",
            "telegram_chat_id": "mock_chat"
        }
        
        # Test short off alias /o1
        notifier.PSA_SO_PENDING_THRESHOLD_MINUTES = 15
        update = {
            "message": {
                "chat": {"id": "mock_chat"},
                "text": "/o1"
            }
        }
        with patch("notifier.send_telegram_notification") as mock_send, \
             patch("notifier.update_render_env_vars_async") as mock_env, \
             patch("notifier.load_config") as mock_load_config:
            mock_load_config.return_value = config
            mock_send.return_value = (True, None)
            notifier.process_long_poll_update(update, config)
            self.assertEqual(notifier.PSA_SO_PENDING_THRESHOLD_MINUTES, 0)
            mock_send.assert_called_with("psa_so_pending_threshold_minutes checker is off.", config)
            
        # Test state switcher is disabled
        update = {
            "message": {
                "chat": {"id": "mock_chat"},
                "text": "/switch_to_render"
            }
        }
        with patch("notifier.send_telegram_notification") as mock_send, \
             patch("notifier.load_config") as mock_load_config:
            mock_load_config.return_value = config
            mock_send.return_value = (True, None)
            notifier.process_long_poll_update(update, config)
            mock_send.assert_called_with("State switching is disabled. Render runs webhook only and Local runs long polling only.", config)

    def test_callmebot_target_validation(self):
        """Test is_valid_callmebot_target and validate_callmebot_user_list."""
        # Test valid targets
        self.assertTrue(notifier.is_valid_callmebot_target("+8801838262248"))
        self.assertTrue(notifier.is_valid_callmebot_target("@UshDhar"))
        self.assertTrue(notifier.is_valid_callmebot_target("UshDhar"))
        self.assertTrue(notifier.is_valid_callmebot_target("ush_dhar"))
        
        # Test invalid targets
        self.assertFalse(notifier.is_valid_callmebot_target("1262260329"))  # pure digits must start with +
        self.assertFalse(notifier.is_valid_callmebot_target("-12"))
        self.assertFalse(notifier.is_valid_callmebot_target("0"))
        self.assertFalse(notifier.is_valid_callmebot_target(""))
        
        # Test user list validator
        self.assertTrue(notifier.validate_callmebot_user_list("UshDhar, +8801838262248"))
        self.assertTrue(notifier.validate_callmebot_user_list("@UshDhar, +8801838262248"))
        self.assertFalse(notifier.validate_callmebot_user_list("UshDhar, 1262260329"))
        self.assertFalse(notifier.validate_callmebot_user_list("-12, +8801838262248"))

if __name__ == '__main__':
    unittest.main()
