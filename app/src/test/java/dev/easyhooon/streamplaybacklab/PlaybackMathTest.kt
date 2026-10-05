package dev.easyhooon.streamplaybacklab

import org.junit.Assert.assertEquals
import org.junit.Test

class PlaybackMathTest {
    @Test fun seekIsBoundedByPlayableTimeline() {
        assertEquals(0L, seekTarget(3_000, -10_000, 120_000))
        assertEquals(120_000L, seekTarget(115_000, 10_000, 120_000))
        assertEquals(15_000L, seekTarget(5_000, 10_000, 120_000))
        assertEquals(0L, seekTarget(0, 10_000, -1))
    }

    @Test fun unknownDurationAndMinuteBoundaryAreReadable() {
        assertEquals("0:00", clockLabel(-1))
        assertEquals("0:59", clockLabel(59_999))
        assertEquals("1:00", clockLabel(60_000))
        assertEquals("120:05", clockLabel(7_205_000))
    }
}
