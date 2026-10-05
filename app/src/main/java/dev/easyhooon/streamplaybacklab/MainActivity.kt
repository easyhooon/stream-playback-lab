package dev.easyhooon.streamplaybacklab

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFF83D6C7))) {
                Surface(Modifier.fillMaxSize()) { PlaybackRoute() }
            }
        }
    }
}

@androidx.annotation.OptIn(UnstableApi::class)
@Composable
private fun PlaybackRoute() {
    val context = LocalContext.current.applicationContext
    val owner = LocalLifecycleOwner.current
    val session = remember(context) { PlaybackSession(context) }
    var savedPosition by rememberSaveable { mutableLongStateOf(0) }
    var savedPlaying by rememberSaveable { mutableStateOf(true) }
    var savedMode by rememberSaveable { mutableStateOf(PlaybackMode.VOD.name) }
    DisposableEffect(session) {
        session.start(savedPosition, savedPlaying, PlaybackMode.valueOf(savedMode))
        onDispose { session.release() }
    }
    DisposableEffect(owner, session) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) session.pauseForBackground()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(session) {
        while (true) {
            session.refresh()
            savedPosition = session.state.positionMs
            savedPlaying = session.player.playWhenReady
            delay(500)
        }
    }
    PlaybackScreen(
        state = session.state,
        onTogglePlayback = session::togglePlayback,
        onSeekBy = session::seekBy,
        onSeekTo = session::seekTo,
        onRetry = session::retry,
        onSelectQuality = session::selectQuality,
        onSelectMode = { session.selectMode(it); savedMode = it.name },
        onGoLive = session::goLive,
        video = {
            AndroidView(
                factory = { viewContext -> PlayerView(viewContext).apply {
                    useController = false
                    player = session.player
                } },
                modifier = Modifier.fillMaxSize(),
                onRelease = { it.player = null },
            )
        },
    )
}

@Composable
fun PlaybackScreen(
    state: PlaybackUiState,
    onTogglePlayback: () -> Unit,
    onSeekBy: (Long) -> Unit,
    onSeekTo: (Long) -> Unit,
    onRetry: () -> Unit,
    onSelectQuality: (Int?) -> Unit,
    video: @Composable () -> Unit,
    modifier: Modifier = Modifier,
    onSelectMode: (PlaybackMode) -> Unit = {},
    onGoLive: () -> Unit = {},
) {
    var scrubbing by remember(state.mode) { mutableStateOf<Float?>(null) }
    Column(modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState())
        .padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("STREAM PLAYBACK LAB", style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.primary)
        Text(state.mode.title, style = MaterialTheme.typography.headlineSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PlaybackMode.entries.forEach { mode ->
                FilterChip(selected = state.mode == mode, onClick = { onSelectMode(mode) }, label = { Text(mode.label) })
            }
        }
        Text("Local experiment · 2s segments · ${if (state.mode == PlaybackMode.LIVE) "ordinary live HLS" else "VOD"}",
            style = MaterialTheme.typography.bodySmall)
        if (state.mode == PlaybackMode.BUNNY) {
            Text("Big Buck Bunny · © 2008 Blender Foundation / www.bigbuckbunny.org · CC BY 3.0. Excerpt, resized and re-encoded. License: creativecommons.org/licenses/by/3.0/",
                style = MaterialTheme.typography.bodySmall)
        }
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(Color.Black)) {
            video()
            if (state.isLoading) CircularProgressIndicator(Modifier.align(Alignment.Center).testTag("loading"))
        }
        Text("${state.status} · ${when { state.isPlaying -> "Playing"; state.playWhenReady -> "Waiting"; else -> "Paused" }}",
            modifier = Modifier.testTag("playback-status"))
        Text("${clockLabel(state.positionMs)} / ${clockLabel(state.durationMs)}")
        Slider(
            value = scrubbing ?: state.positionMs.toFloat(),
            onValueChange = { scrubbing = it },
            onValueChangeFinished = { scrubbing?.let { onSeekTo(it.toLong()) }; scrubbing = null },
            valueRange = 0f..state.durationMs.coerceAtLeast(1).toFloat(),
            enabled = state.durationMs > 0 && state.error == null,
            modifier = Modifier.testTag("seek-slider"),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { onSeekBy(-10_000) }, enabled = state.durationMs > 0 && state.error == null) {
                Text("−10s")
            }
            Button(onClick = onTogglePlayback, enabled = state.error == null,
                modifier = Modifier.testTag("play-pause")) {
                Text(if (state.status == "ENDED") "Replay" else if (state.playWhenReady) "Pause" else "Play")
            }
            OutlinedButton(onClick = { onSeekBy(10_000) }, enabled = state.durationMs > 0 && state.error == null) {
                Text("+10s")
            }
        }
        if (state.mode == PlaybackMode.LIVE) {
            Button(onClick = onGoLive, modifier = Modifier.testTag("go-live")) { Text("Go live") }
            Text("Live offset: ${state.liveOffsetMs?.let { "%.1fs".format(java.util.Locale.US, it / 1000f) } ?: "—"} · target 6.0s",
                modifier = Modifier.testTag("live-offset"))
            Text("Live window: ${clockLabel(state.durationMs)} · dynamic=${state.isDynamic}")
            state.liveEdgeUnixMs?.let {
                Text("Window edge UTC: ${java.time.Instant.ofEpochMilli(it)}", style = MaterialTheme.typography.bodySmall)
            }
        }
        state.error?.let { error ->
            Text("Error: $error", color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("error"))
            Button(onClick = onRetry, modifier = Modifier.testTag("retry")) { Text("Retry") }
        }
        Text("Quality mode", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = state.qualityOverride == null, onClick = { onSelectQuality(null) }, label = { Text("Auto") })
            state.availableHeights.forEach { height ->
                FilterChip(selected = state.qualityOverride == height, onClick = { onSelectQuality(height) },
                    label = { Text("${height}p") })
            }
        }
        Text("Request: ${state.requestedQuality}", modifier = Modifier.testTag("request-quality"))
        Text("Decoder: ${state.decodedQuality}", modifier = Modifier.testTag("decoder-quality"))
        Text("Buffer: ${"%.1f".format(java.util.Locale.US, state.bufferMs / 1000f)}s · Estimate: ${state.estimateKbps} kbps")
        Text("Events", style = MaterialTheme.typography.titleMedium)
        state.events.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
        Spacer(Modifier.height(8.dp))
    }
}
