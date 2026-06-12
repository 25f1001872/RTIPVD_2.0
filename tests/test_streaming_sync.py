import unittest

from src.streaming.sync import GPSSyncBuffer, _raw_gps_to_decimal, _div100_ddmm_to_decimal


class TestGPSConversionFormula(unittest.TestCase):
    """Test exact user-specified conversion: value/100, then fractional / 0.6"""

    def test_raw_gps_div100_exact_formula(self):
        """Test: 2951.6747 → /100 = 29.516747 → frac/0.6 = 0.861245 → 29.861245"""
        result = _raw_gps_to_decimal(2951.6747, max_degrees=90.0)
        self.assertAlmostEqual(result, 29.861245, places=5)

    def test_raw_gps_lon_div100_exact_formula(self):
        """Test: 7753.8555 → /100 = 77.538555 → frac/0.6 = 0.897592 → 77.897592"""
        result = _raw_gps_to_decimal(7753.8555, max_degrees=180.0)
        self.assertAlmostEqual(result, 77.897592, places=5)

    def test_div100_ddmm_intermediate_form(self):
        """Test intermediate form (after /100 but before /0.6)"""
        result = _div100_ddmm_to_decimal(29.516747, max_degrees=90.0)
        self.assertAlmostEqual(result, 29.861245, places=5)

    def test_div100_negative_values(self):
        """Test negative latitude/longitude conversion"""
        result = _raw_gps_to_decimal(-2951.6747, max_degrees=90.0)
        self.assertAlmostEqual(result, -29.861245, places=5)

    def test_div100_negative_lon(self):
        """Test negative longitude conversion"""
        result = _raw_gps_to_decimal(-7753.8555, max_degrees=180.0)
        self.assertAlmostEqual(result, -77.897592, places=5)


class GPSSyncBufferParseFixTests(unittest.TestCase):
    def test_converts_raw_ddmm_coords_to_decimal(self):
        fix = GPSSyncBuffer.parse_fix(
            {
                "timestamp": "2026-04-25T10:00:00Z",
                "lat": 2951.6747,
                "lon": 7753.8555,
                "fix": True,
                "source": "stream",
            }
        )

        self.assertTrue(fix.fix)
        self.assertAlmostEqual(fix.latitude, 29.861245, places=5)
        self.assertAlmostEqual(fix.longitude, 77.897592, places=5)

    def test_converts_negative_raw_ddmm_coords_to_decimal(self):
        fix = GPSSyncBuffer.parse_fix(
            {
                "timestamp": "2026-04-25T10:00:00Z",
                "latitude": -2951.6747,
                "longitude": -7753.8555,
                "fix": True,
                "source": "stream",
            }
        )

        self.assertTrue(fix.fix)
        self.assertAlmostEqual(fix.latitude, -29.861245, places=5)
        self.assertAlmostEqual(fix.longitude, -77.897592, places=5)

    def test_keeps_decimal_degrees_unchanged(self):
        fix = GPSSyncBuffer.parse_fix(
            {
                "timestamp": "2026-04-25T10:00:00Z",
                "latitude": 29.861245,
                "longitude": 77.897592,
                "fix": True,
                "source": "stream",
            }
        )

        self.assertTrue(fix.fix)
        self.assertAlmostEqual(fix.latitude, 29.861245, places=5)
        self.assertAlmostEqual(fix.longitude, 77.897592, places=5)


if __name__ == "__main__":
    unittest.main()
