"""Library-loan design evaluation fixture."""

from __future__ import annotations


class Library:
    def __init__(self) -> None:
        self._waived = 0

    def fee(self, days: int) -> int:
        quotes = (
            self.book(days),
            self.dvd(days),
            self.ebook(days),
            self.journal(days),
            self.magazine(days),
            self.atlas(days),
            self.map(days),
            self.score(days),
            self.vinyl(days),
            self.cd(days),
            self.cassette(days),
            self.game(days),
            self.puzzle(days),
            self.toy(days),
            self.kit(days),
            self.tablet(days),
            self.laptop(days),
            self.camera(days),
            self.projector(days),
            self.reader(days),
            self.braille(days),
            self.large_print(days),
            self.comic(days),
            self.manga(days),
            self.pamphlet(days),
            self.microfilm(days),
            self.archive(days),
            self.poster(days),
            self.slide(days),
            self.manuscript(days),
        )
        return sum(quotes) // len(quotes)

    def book(self, days: int) -> int:
        """Calculate the book circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def dvd(self, days: int) -> int:
        """Calculate the dvd circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def ebook(self, days: int) -> int:
        """Calculate the ebook circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def journal(self, days: int) -> int:
        """Calculate the journal circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def magazine(self, days: int) -> int:
        """Calculate the magazine circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def atlas(self, days: int) -> int:
        """Calculate the atlas circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def map(self, days: int) -> int:
        """Calculate the map circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def score(self, days: int) -> int:
        """Calculate the score circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def vinyl(self, days: int) -> int:
        """Calculate the vinyl circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def cd(self, days: int) -> int:
        """Calculate the cd circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def cassette(self, days: int) -> int:
        """Calculate the cassette circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def game(self, days: int) -> int:
        """Calculate the game circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def puzzle(self, days: int) -> int:
        """Calculate the puzzle circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def toy(self, days: int) -> int:
        """Calculate the toy circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def kit(self, days: int) -> int:
        """Calculate the kit circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def tablet(self, days: int) -> int:
        """Calculate the tablet circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def laptop(self, days: int) -> int:
        """Calculate the laptop circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def camera(self, days: int) -> int:
        """Calculate the camera circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def projector(self, days: int) -> int:
        """Calculate the projector circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def reader(self, days: int) -> int:
        """Calculate the reader circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def braille(self, days: int) -> int:
        """Calculate the braille circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def large_print(self, days: int) -> int:
        """Calculate the large print circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def comic(self, days: int) -> int:
        """Calculate the comic circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def manga(self, days: int) -> int:
        """Calculate the manga circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def pamphlet(self, days: int) -> int:
        """Calculate the pamphlet circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def microfilm(self, days: int) -> int:
        """Calculate the microfilm circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def archive(self, days: int) -> int:
        """Calculate the archive circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def poster(self, days: int) -> int:
        """Calculate the poster circulation tariff."""
        rate = 1
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def slide(self, days: int) -> int:
        """Calculate the slide circulation tariff."""
        rate = 2
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge

    def manuscript(self, days: int) -> int:
        """Calculate the manuscript circulation tariff."""
        rate = 3
        grace = self._waived
        remaining = max(0, days - grace)
        charge = 0
        weeks = remaining // 7
        weekdays = remaining % 7
        for _ in range(weeks):
            monday = rate
            tuesday = rate
            wednesday = rate
            thursday = rate
            friday = rate
            weekend = rate * 2
            charge += monday + tuesday + wednesday
            charge += thursday + friday + weekend
        for _ in range(weekdays):
            charge += rate
        return charge
