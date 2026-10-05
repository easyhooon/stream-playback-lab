package dev.easyhooon.streamplaybacklab

import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class PlaybackScreenTest {
    @get:Rule val compose = createComposeRule()

    @Test fun bufferingKeepsPauseIntentVisible() {
        compose.setContent {
            MaterialTheme {
                PlaybackScreen(PlaybackUiState(status = "BUFFERING", isLoading = true, playWhenReady = true),
                    onTogglePlayback = {}, onSeekBy = {}, onSeekTo = {}, onRetry = {},
                    onSelectQuality = {}, video = {})
            }
        }
        compose.onNodeWithTag("loading").assertIsDisplayed()
        compose.onNodeWithText("Pause").assertIsDisplayed()
    }

    @Test fun errorExposesRetryAndPreventsPlayback() {
        var retries = 0
        compose.setContent {
            MaterialTheme {
                PlaybackScreen(PlaybackUiState(error = "ERROR_CODE_IO_BAD_HTTP_STATUS"),
                    onTogglePlayback = {}, onSeekBy = {}, onSeekTo = {},
                    onRetry = { retries++ }, onSelectQuality = {}, video = {})
            }
        }
        compose.onNodeWithTag("error").assertIsDisplayed()
        compose.onNodeWithTag("play-pause").assertIsNotEnabled()
        compose.onNodeWithTag("retry").performClick()
        assertEquals(1, retries)
    }

    @Test fun transportControlsAndQualityInvokeUserIntent() {
        var toggles = 0
        var delta = 0L
        var quality: Int? = null
        compose.setContent {
            MaterialTheme {
                PlaybackScreen(PlaybackUiState(status = "READY", isPlaying = true, playWhenReady = true,
                    durationMs = 120_000, availableHeights = listOf(360, 720)),
                    onTogglePlayback = { toggles++ }, onSeekBy = { delta = it }, onSeekTo = {},
                    onRetry = {}, onSelectQuality = { quality = it }, video = {})
            }
        }
        compose.onNodeWithText("Pause").performClick()
        compose.onNodeWithText("+10s").performClick()
        compose.onNodeWithText("360p").performScrollTo().performClick()
        assertEquals(1, toggles)
        assertEquals(10_000L, delta)
        assertEquals(360, quality)
    }

    @Test fun liveSourceAndReturnExposeExplicitIntentAndOffset() {
        var chosen: PlaybackMode? = null
        var returns = 0
        compose.setContent {
            MaterialTheme {
                PlaybackScreen(PlaybackUiState(mode = PlaybackMode.LIVE, isLive = true,
                    isDynamic = true, liveOffsetMs = 6_500, durationMs = 12_000),
                    onTogglePlayback = {}, onSeekBy = {}, onSeekTo = {}, onRetry = {},
                    onSelectQuality = {}, video = {}, onSelectMode = { chosen = it },
                    onGoLive = { returns++ })
            }
        }
        compose.onNodeWithText("VOD").performClick()
        compose.onNodeWithTag("go-live").performScrollTo().performClick()
        compose.onNodeWithTag("live-offset").performScrollTo().assertIsDisplayed()
        assertEquals(PlaybackMode.VOD, chosen)
        assertEquals(1, returns)
    }
}
