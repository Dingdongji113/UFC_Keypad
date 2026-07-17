import unittest

from case1_clearing_turn.heading import first_target_heading, normalize_heading, shortest_heading_error


class HeadingTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_heading(360), 0)
        self.assertEqual(normalize_heading(-10), 350)

    def test_wrap_errors(self):
        cases = [(1, 359, 2), (359, 1, -2), (10, 350, 20), (350, 10, -20)]
        for target, current, expected in cases:
            with self.subTest(target=target, current=current):
                self.assertEqual(shortest_heading_error(target, current), expected)

    def test_cat_targets_use_launch_heading(self):
        cases = [(1, 350, 10), (2, 100, 120), (3, 10, 350), (4, 270, 250)]
        for cat, launch, expected in cases:
            self.assertEqual(first_target_heading(cat, launch), expected)

    def test_invalid_cat(self):
        with self.assertRaises(ValueError):
            first_target_heading(5, 0)


if __name__ == "__main__":
    unittest.main()
