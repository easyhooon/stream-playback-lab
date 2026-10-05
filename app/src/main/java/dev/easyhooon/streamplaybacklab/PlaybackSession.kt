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
import androidx.media3.common.Timeline
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

enum class PlaybackMode(val path: String, val title: String, val label: String) {
    VOD("hls/master.m3u8", "Synthetic HLS VOD", "VOD"),
    BUNNY("bbb/master.m3u8", "Big Buck Bunny · HLS VOD", "Bunny"),
    LIVE("live/index.m3u8", "Synthetic live HLS", "Live"),
}

data class PlaybackUiState(
    val mode: PlaybackMode = PlaybackMode.VOD,
    val status: String = "IDLE",
    val isPlaying: Boolean = false,
    val playWhenReady: Boolean = false,
    val isLoading: Boolean = false,
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val bufferMs: Long = 0,
    val isLive: Boolean = false,
    val isDynamic: Boolean = false,
    val liveOffsetMs: Long? = null,
    val liveEdgeUnixMs: Long? = null,
    val defaultPositionMs: Long? = null,
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
    private var lastLiveLogMs = 0L
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
            override fun onTimelineChanged(timeline: Timeline, reason: Int) {
                if (state.mode == PlaybackMode.LIVE) {
                    refresh()
                    event("live_window live=${state.isLive} dynamic=${state.isDynamic} window_ms=${state.durationMs} edge_unix_ms=${state.liveEdgeUnixMs}")
                }
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

            override fun onAudioInputFormatChanged(
                eventTime: AnalyticsListener.EventTime,
                format: Format,
                decoderReuseEvaluation: DecoderReuseEvaluation?,
            ) {
                event("audio_format mime=${format.sampleMimeType} channels=${format.channelCount}")
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

    fun start(positionMs: Long, playWhenReady: Boolean, mode: PlaybackMode = PlaybackMode.VOD) {
        state = state.copy(mode = mode)
        player.setMediaItem(mediaItem(mode))
        if (mode != PlaybackMode.LIVE) player.seekTo(positionMs)
        player.prepare()
        player.playWhenReady = playWhenReady
    }

    fun refresh() {
        val window = if (player.currentTimeline.isEmpty) null else
            player.currentTimeline.getWindow(player.currentMediaItemIndex, Timeline.Window())
        val offset = player.currentLiveOffset.takeIf { it != C.TIME_UNSET && it >= 0 }
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
            isLive = player.isCurrentMediaItemLive,
            isDynamic = player.isCurrentMediaItemDynamic,
            liveOffsetMs = offset,
            liveEdgeUnixMs = window?.windowStartTimeMs?.takeIf { it != C.TIME_UNSET }?.let {
                if (player.duration > 0) it + player.duration else null
            },
            defaultPositionMs = window?.defaultPositionMs?.takeIf { it != C.TIME_UNSET },
            availableHeights = heights,
            error = player.playerError?.errorCodeName,
        )
        val now = SystemClock.elapsedRealtime()
        if (state.mode == PlaybackMode.LIVE && now - lastLiveLogMs >= 1_000 && offset != null) {
            lastLiveLogMs = now
            Log.i(TAG, "event=live_metrics offset_ms=$offset window_ms=${state.durationMs} dynamic=${state.isDynamic} playing=${state.isPlaying}")
        }
    }

    fun togglePlayback() {
        if (player.playbackState == Player.STATE_ENDED) {
            event("replay")
            player.seekTo(0)
            player.play()
        } else if (player.playWhenReady) player.pause() else {
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
        // A restarted producer has a new sequence/time origin: reload its fresh live window.
        if (state.mode == PlaybackMode.LIVE) player.setMediaItem(mediaItem(PlaybackMode.LIVE))
        player.prepare()
        player.play()
    }

    fun selectMode(mode: PlaybackMode) {
        if (state.mode == mode) return
        player.trackSelectionParameters = player.trackSelectionParameters.buildUpon()
            .clearOverridesOfType(C.TRACK_TYPE_VIDEO).build()
        state = PlaybackUiState(mode = mode, events = state.events)
        event("source_mode=$mode")
        start(0, true, mode)
    }

    fun goLive() {
        if (state.mode != PlaybackMode.LIVE) return
        event("go_live offset_before_ms=${state.liveOffsetMs}")
        if (player.playerError != null) retry() else {
            player.seekToDefaultPosition()
            player.play()
        }
    }

    private fun mediaItem(mode: PlaybackMode): MediaItem {
        val builder = MediaItem.Builder().setUri("http://127.0.0.1:8090/${mode.path}")
        if (mode == PlaybackMode.LIVE) builder.setLiveConfiguration(
            MediaItem.LiveConfiguration.Builder().setTargetOffsetMs(6_000)
                .setMinPlaybackSpeed(0.97f).setMaxPlaybackSpeed(1.03f).build())
        return builder.build()
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

    private fun quality(format: Format): String {
        val rate = if (format.bitrate > 0) "${format.bitrate / 1000} kbps" else "bitrate unknown"
        return "${format.height}p · $rate"
    }
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
