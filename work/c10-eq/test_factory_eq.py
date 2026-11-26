import math
import struct
import unittest
from factory_eq_probe import FactoryEQ


def configured(gains):
    p = FactoryEQ()
    p.open()
    result, fmt = p.configure(gains)
    assert result == 1 and fmt[2:] == (44100, 2, 29, 4)
    return p


def sine(frequency, frames=1024):
    return [x for i in range(frames) for x in
            [0.02 * math.sin(2 * math.pi * frequency * i / 44100)] * 2]


class OriginalDSPTests(unittest.TestCase):
    def test_flat_is_exact_for_float_input(self):
        p = configured([0] * 10)
        samples = sine(1000, 256)
        samples = list(struct.unpack('<' + 'f' * len(samples), struct.pack('<' + 'f' * len(samples), *samples)))
        self.assertEqual(p.process(samples), samples)

    def test_ten_bands_set_and_query_back(self):
        values = [-12, -9, -6, -3, 0, 1, 3, 6, 9, 12]
        p = configured(values)
        for channel in range(2):
            p.u.mem_write(p.argument, struct.pack('<II', p.gains, channel))
            self.assertEqual(p.call(0x442f44, p.af, 0x40001d01, p.argument), 1)
            actual = struct.unpack('<10f', p.u.mem_read(p.gains, 40))
            for wanted, found in zip(values, actual):
                self.assertAlmostEqual(wanted, found, places=3)

    def test_no_left_to_right_channel_leakage(self):
        p = configured([6, 3, 0, 0, 0, 0, 0, 0, 0, 0])
        samples = [x for i in range(256) for x in [0.02 if i == 0 else 0, 0]]
        output = p.process(samples)
        self.assertEqual(output[1::2], [0] * 256)
        self.assertNotEqual(output[0::2], samples[0::2])

    def test_one_khz_band_changes_spectral_balance(self):
        gains = [0] * 10
        gains[5] = 6
        ratios = []
        for frequency in [100, 1000]:
            p = configured(gains)
            samples = sine(frequency)
            output = p.process(samples)
            source_energy = sum(x * x for x in samples[-1024:])
            output_energy = sum(x * x for x in output[-1024:])
            ratios.append(10 * math.log10(output_energy / source_energy))
        self.assertGreater(ratios[1] - ratios[0], 4.5)
        self.assertLess(ratios[1] - ratios[0], 7.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
