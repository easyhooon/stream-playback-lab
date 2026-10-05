package dev.easyhooon.streamplaybacklab

import android.content.Context
import android.os.SystemClock
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.common.C
import androidx.media3.common.Format
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.PlaybackException
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener
import androidx.media3.exoplayer.source.LoadEventInfo
import androidx.media3.exoplayer.source.MediaLoadData
import androidx.media3.exoplayer.upstream.DefaultBandwidthMeter
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.exoplayer.DecoderReuseEvaluation
import java.io.IOException

data class PlaybackUiState(
    val status: String = "IDLE",
    val isPlaying: Boolean = false,
    val playWhenReady: Boolean = false,
    val isLoading: Boolean = false,
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val bufferMs: Long = 0,
    val requestedQuality: String = "—",
    val decodedQuality: String = "—",
    val estimateKbps: Long = 0,
    val availableHeights: List<Int> = emptyList(),
    val qualityOverride: Int? = null,
    val error: String? = null,
    val events: List<String> = emptyList(),
)

fun seekTarget(positionMs: Long, deltaMs: Long, durationMs: Long): Long =
    (positionMs + deltaMs).coerceIn(0, durationMs.coerceAtLeast(0))

fun clockLabel(timeMs: Long): String {
    val seconds = timeMs.coerceAtLeast(0) / 1000
    return "%d:%02d".format(java.util.Locale.US, seconds / 60, seconds % 60)
}

@androidx.annotation.OptIn(UnstableApi::class)
class PlaybackSession(context: Context) {
    private val started = SystemClock.elapsedRealtime()
    private val meter = DefaultBandwidthMeter.Builder(context)
        .setInitialBitrateEstimate(6_000_000)
        .build()
    val player: ExoPlayer = ExoPlayer.Builder(context)
        .setBandwidthMeter(meter)
        .setLoadControl(DefaultLoadControl.Builder()
            .setBufferDurationsMs(3_000, 15_000, 500, 1_000)
            .build())
        .setMediaSourceFactory(DefaultMediaSourceFactory(context)
            .setLoadErrorHandlingPolicy(DefaultLoadErrorHandlingPolicy(2)))
        .build()
    var state by mutableStateOf(PlaybackUiState())
        private set

    init {
        player.addListener(object : Player.Listener {
            override fun onEvents(player: Player, events: Player.Events) = refresh()
            override fun onPlaybackStateChanged(playbackState: Int) {
                event("state=${status(playbackState)} position_ms=${player.currentPosition}")
            }
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                event("playing=$isPlaying position_ms=${player.currentPosition}")
            }
            override fun onPlayerError(error: PlaybackException) {
                event("player_error code=${error.errorCodeName} position_ms=${player.currentPosition}")
            }
        })
        player.addAnalyticsListener(object : AnalyticsListener {
            override fun onDownstreamFormatChanged(
                eventTime: AnalyticsListener.EventTime,
                mediaLoadData: MediaLoadData,
            ) {
                val format = mediaLoadData.trackFormat ?: return
                // Muxed HLS chunks can report TRACK_TYPE_DEFAULT rather than VIDEO.
                if (format.height <= 0) return
                state = state.copy(requestedQuality = quality(format))
                val reason = when (mediaLoadData.trackSelectionReason) {
                    C.SELECTION_REASON_ADAPTIVE -> "ADAPTIVE"
                    C.SELECTION_REASON_MANUAL -> "MANUAL"
                    C.SELECTION_REASON_INITIAL -> "INITIAL"
                    else -> mediaLoadData.trackSelectionReason.toString()
                }
                event("request_format height=${format.height} bitrate=${format.bitrate} reason=$reason track_type=${mediaLoadData.trackType} position_ms=${player.currentPosition}")
            }

            override fun onVideoInputFormatChanged(
                eventTime: AnalyticsListener.EventTime,
                format: Format,
                decoderReuseEvaluation: DecoderReuseEvaluation?,
            ) {
                state = state.copy(decodedQuality = quality(format))
                event("decoder_format height=${format.height} bitrate=${format.bitrate} position_ms=${player.currentPosition}")
            }

            override fun onBandwidthEstimate(
                eventTime: AnalyticsListener.EventTime,
                totalLoadTimeMs: Int,
                totalBytesLoaded: Long,
                bitrateEstimate: Long,
            ) {
                state = state.copy(estimateKbps = bitrateEstimate / 1000)
                Log.i(TAG, "event=bandwidth estimate_kbps=${bitrateEstimate / 1000} bytes=$totalBytesLoaded elapsed_ms=$totalLoadTimeMs")
            }

            override fun onLoadError(
                eventTime: AnalyticsListener.EventTime,
                loadEventInfo: LoadEventInfo,
                mediaLoadData: MediaLoadData,
                error: IOException,
                wasCanceled: Boolean,
            ) {
                event("load_error type=${error.javaClass.simpleName} canceled=$wasCanceled path=${loadEventInfo.uri.path}")
            }
        })
    }

    fun start(positionMs: Long, playWhenReady: Boolean) {
        player.setMediaItem(MediaItem.fromUri(PLAYLIST_URL))
        player.seekTo(positionMs)
        player.prepare()
        player.playWhenReady = playWhenReady
    }

    fun refresh() {
        val heights = player.currentTracks.groups.filter { it.type == C.TRACK_TYPE_VIDEO }
            .flatMap { group -> (0 until group.length).filter(group::isTrackSupported)
                .map { group.getTrackFormat(it).height }.filter { it > 0 } }
            .distinct().sorted()
        state = state.copy(
            status = status(player.playbackState),
            isPlaying = player.isPlaying,
            playWhenReady = player.playWhenReady,
            isLoading = player.playbackState == Player.STATE_BUFFERING,
            positionMs = player.currentPosition.coerceAtLeast(0),
            durationMs = player.duration.coerceAtLeast(0),
            bufferMs = player.totalBufferedDuration.coerceAtLeast(0),
            availableHeights = heights,
            error = player.playerError?.errorCodeName,
        )
    }

    fun togglePlayback() {
        if (player.playWhenReady) player.pause() else {
            if (player.playbackState == Player.STATE_ENDED) player.seekTo(0)
            player.play()
        }
    }

    fun seekTo(positionMs: Long) {
        val target = positionMs.coerceIn(0, player.duration.coerceAtLeast(0))
        event("seek target_ms=$target")
        player.seekTo(target)
        refresh()
    }

    fun seekBy(deltaMs: Long) = seekTo(seekTarget(player.currentPosition, deltaMs, player.duration))

    fun retry() {
        event("retry position_ms=${player.currentPosition}")
        player.prepare()
        player.play()
    }

    fun selectQuality(height: Int?) {
        val parameters = player.trackSelectionParameters.buildUpon()
            .clearOverridesOfType(C.TRACK_TYPE_VIDEO)
        if (height != null) {
            val group = player.currentTracks.groups.firstOrNull { group ->
                group.type == C.TRACK_TYPE_VIDEO && (0 until group.length).any {
                    group.isTrackSupported(it) && group.getTrackFormat(it).height == height
                }
            } ?: return
            val index = (0 until group.length).first {
                group.isTrackSupported(it) && group.getTrackFormat(it).height == height
            }
            parameters.setOverrideForType(TrackSelectionOverride(group.mediaTrackGroup, index))
        }
        player.trackSelectionParameters = parameters.build()
        state = state.copy(qualityOverride = height)
        event("quality_mode=${height?.let { "${it}p" } ?: "AUTO"}")
    }

    fun pauseForBackground() = player.pause()
    fun release() = player.release()

    private fun event(message: String) {
        val line = "${(SystemClock.elapsedRealtime() - started) / 1000}s $message"
        state = state.copy(events = (state.events + line).takeLast(8))
        Log.i(TAG, "event=$message")
    }

    private fun quality(format: Format) = "${format.height}p · ${format.bitrate / 1000} kbps"
    private fun status(value: Int) = when (value) {
        Player.STATE_BUFFERING -> "BUFFERING"
        Player.STATE_READY -> "READY"
        Player.STATE_ENDED -> "ENDED"
        else -> "IDLE"
    }

    companion object {
        const val PLAYLIST_URL = "http://127.0.0.1:8090/hls/master.m3u8"
        const val TAG = "PlaybackLab"
    }
}
