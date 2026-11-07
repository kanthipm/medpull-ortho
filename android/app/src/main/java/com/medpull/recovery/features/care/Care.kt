package com.medpull.recovery.features.care

import androidx.compose.ui.graphics.Color
import com.medpull.recovery.ui.PrimaryButton
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import com.medpull.recovery.features.today.DOT
import com.medpull.recovery.ui.BubbleBrush
import com.medpull.recovery.ui.CapsuleShape
import com.medpull.recovery.ui.MPType
import com.medpull.recovery.ui.glassSurface
import com.medpull.recovery.ui.grain
import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import androidx.navigation.NavHostController
import coil.compose.AsyncImage
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.core.ChatAttachment
import com.medpull.recovery.core.ChatMessage
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.Tab
import com.medpull.recovery.core.uploadAttachment
import com.medpull.recovery.core.withdrawAttachment
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Initials
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.Tone
import com.medpull.recovery.ui.appModel
import java.io.File
import java.util.Locale
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

private val QUICK_LOG = listOf("My pain is a ", "I did my exercises", "I walked today", "A note for my nurse: ")

/**
 * One thread with the care team: typed text goes to the thread; the mic and
 * the quick-log chips go to the copilot, which logs pain, marks tasks done or
 * passes a note along, and whose reply is spoken when the question was.
 */
@Composable
fun CareScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val graph = (context.applicationContext as MedPullApp).graph
    val scope = rememberCoroutineScope()
    val c = MP.colors
    val speech = remember { SpeechController(context) }
    val recorder = remember { VoiceNoteRecorder(context) }
    val cache = remember { MediaCache(context, graph.api) }
    DisposableEffect(Unit) { onDispose { speech.release(); recorder.cancel() } }

    var draft by remember { mutableStateOf("") }
    var toAssistant by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    var thinking by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var uploading by remember { mutableStateOf(false) }
    val pending = remember { mutableStateListOf<ChatAttachment>() }
    val turns = remember { mutableStateListOf<Pair<Boolean, String>>() }   // copilot turns, this session only
    var menuOpen by remember { mutableStateOf(false) }
    var captureUri by remember { mutableStateOf<Uri?>(null) }
    val listening by speech.listening.collectAsStateWithLifecycle()
    val transcript by speech.transcript.collectAsStateWithLifecycle()
    val speechError by speech.error.collectAsStateWithLifecycle()
    var recordingNote by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()

    // Load, mark read, then poll every 20 s while this screen is visible.
    LaunchedEffect(Unit) {
        app.refreshMessages(false); app.markMessagesRead()
        while (isActive) { delay(20_000); app.refreshMessages(false) }
    }
    LaunchedEffect(state.messages.size, turns.size) {
        val n = state.messages.size + turns.size
        if (n > 0) listState.animateScrollToItem(n - 1)
    }

    suspend fun attach(uri: Uri) {
        if (pending.size >= 4) { error = "Up to four files at a time."; return }
        uploading = true
        try {
            val p = AttachmentPrep.fromUri(context, uri) ?: throw IllegalStateException("That file type isn't supported.")
            pending.add(graph.api.uploadAttachment(p.bytes, p.contentType, p.filename))
        } catch (e: Exception) { error = e.message }
        uploading = false
    }

    val pickMedia = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(4)) { uris ->
        scope.launch { uris.forEach { attach(it) } }
    }
    val pickFiles = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        scope.launch { uris.forEach { attach(it) } }
    }
    val takePhoto = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val u = captureUri; if (ok && u != null) scope.launch { attach(u) }
    }
    val takeVideo = rememberLauncherForActivityResult(ActivityResultContracts.CaptureVideo()) { ok ->
        val u = captureUri; if (ok && u != null) scope.launch { attach(u) }
    }
    val askCamera = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    val askMic = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) speech.startListening() else error = "Microphone access is needed to talk."
    }

    fun captureFile(ext: String): Uri {
        val f = File(context.cacheDir, "captures/capture-${System.currentTimeMillis()}.$ext").apply { parentFile?.mkdirs() }
        return FileProvider.getUriForFile(context, "${context.packageName}.files", f).also { captureUri = it }
    }

    suspend fun send(text: String, channel: String, speak: Boolean) {
        val t = text.trim()
        if (t.isEmpty() && pending.isEmpty()) return
        sending = true
        try {
            if (toAssistant || channel == "voice") {
                turns.add(true to t); thinking = true
                val r = app.ask(t, channel)
                thinking = false
                turns.add(false to r.reply + if (r.flagged) "\n\nPassed to your care team." else "")
                if (speak) speech.speak(r.reply)
            } else {
                app.send(t, pending.map { it.id })
                pending.clear()
            }
            draft = ""; toAssistant = false
        } catch (e: Exception) { error = e.message; thinking = false }
        sending = false
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        CareHeader(state.me?.patient?.careTeam.orEmpty())
        (error ?: speechError ?: state.lastError)?.let {
            ErrorBanner(it, Modifier.padding(horizontal = 16.dp), onDismiss = { error = null; app.clearError() }); Gap(8.dp)
        }
        LazyColumn(state = listState, modifier = Modifier.weight(1f).fillMaxWidth(), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (state.messages.isEmpty()) item { IntroCard() }
            items(state.messages, key = { it.id }) { m -> Bubble(m, cache, onOpenTask = { id ->
                scope.launch { app.refreshTasks(false) }
                app.handle(Uri.parse("${app.config.scheme}://tasks/$id"))
            }) }
            items(turns) { (mine, text) -> TurnBubble(mine, text) }
            if (thinking) item { TurnBubble(false, "…") }
        }
        if (listening) {
            Text(if (transcript.isBlank()) "Listening…" else transcript, color = c.muted, style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp))
        }
        if (pending.isNotEmpty()) {
            LazyRow(Modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(pending, key = { it.id }) { a ->
                    Row(Modifier.clip(RoundedCornerShape(999.dp)).background(c.soft).padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(a.filename ?: a.kind, style = MaterialTheme.typography.labelMedium, color = c.ink)
                        IconButton(onClick = { scope.launch { try { graph.api.withdrawAttachment(a.id) } catch (_: Exception) {}; pending.remove(a) } }, modifier = Modifier.size(28.dp)) {
                            Icon(Icons.Default.Close, "Remove", modifier = Modifier.size(16.dp), tint = c.muted)
                        }
                    }
                }
            }
            Gap(6.dp)
        }
        if (draft.isBlank() && pending.isEmpty() && !listening) {
            LazyRow(Modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item { Text("Quick log", style = MPType.labelMedium, color = c.muted, modifier = Modifier.padding(top = 9.dp)) }
                items(QUICK_LOG) { q -> QuickChip(q.trim() + if (q.endsWith(" ") || q.endsWith(": ")) "…" else "") { draft = q; toAssistant = true } }
            }
            Gap(6.dp)
        }
        if (toAssistant && draft.isNotBlank()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.AutoAwesome, null, tint = c.brandInk, modifier = Modifier.size(14.dp))
                Spacer(Modifier.width(6.dp))
                Text("To MedPull, which logs it for you", style = MaterialTheme.typography.labelMedium, color = c.brandInk)
                Spacer(Modifier.weight(1f))
                PlainButton("Clear", color = c.muted) { draft = ""; toAssistant = false }
            }
        }
        if (recordingNote) RecordingBar(
            onCancel = { recorder.cancel(); recordingNote = false },
            onStop = {
                recordingNote = false
                recorder.stop()?.let { p -> scope.launch { uploading = true; try { pending.add(graph.api.uploadAttachment(p.bytes, p.contentType, p.filename)) } catch (e: Exception) { error = e.message }; uploading = false } }
            },
        ) else Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box {
                ComposerRound(Icons.Default.Add, enabled = !uploading && pending.size < 4 && !listening) { menuOpen = true }
                DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    DropdownMenuItem(text = { Text("Take a photo") }, leadingIcon = { Icon(Icons.Default.PhotoCamera, null) }, onClick = {
                        menuOpen = false
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) askCamera.launch(Manifest.permission.CAMERA)
                        else takePhoto.launch(captureFile("jpg"))
                    })
                    DropdownMenuItem(text = { Text("Record a video") }, leadingIcon = { Icon(Icons.Default.Videocam, null) }, onClick = {
                        menuOpen = false
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) askCamera.launch(Manifest.permission.CAMERA)
                        else takeVideo.launch(captureFile("mp4"))
                    })
                    DropdownMenuItem(text = { Text("Photo library") }, leadingIcon = { Icon(Icons.Default.PhotoLibrary, null) }, onClick = {
                        menuOpen = false; pickMedia.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                    })
                    DropdownMenuItem(text = { Text(if (recordingNote) "Stop recording" else "Record a voice note") }, leadingIcon = { Icon(if (recordingNote) Icons.Default.Stop else Icons.Default.Mic, null) }, onClick = {
                        menuOpen = false
                        if (recordingNote) {
                            recordingNote = false
                            recorder.stop()?.let { p -> scope.launch { uploading = true; try { pending.add(graph.api.uploadAttachment(p.bytes, p.contentType, p.filename)) } catch (e: Exception) { error = e.message }; uploading = false } }
                        } else if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                            try { recorder.start(); recordingNote = true } catch (e: Exception) { error = "Couldn't start recording." }
                        } else askMic.launch(Manifest.permission.RECORD_AUDIO)
                    })
                    DropdownMenuItem(text = { Text("Choose a file") }, leadingIcon = { Icon(Icons.Default.AttachFile, null) }, onClick = {
                        menuOpen = false; pickFiles.launch(AttachmentPrep.acceptedMimes)
                    })
                }
            }
            ComposerField(
                text = draft, onChange = { draft = it; if (it.isEmpty()) toAssistant = false },
                placeholder = if (listening) "Listening…" else if (recordingNote) "Recording a voice note…" else if (toAssistant) "Ask MedPull" else "Write to your care team",
                canSend = !sending && !uploading && !listening && (draft.isNotBlank() || pending.isNotEmpty()), busy = sending,
                modifier = Modifier.weight(1f),
            ) { scope.launch { send(draft, "app", speak = false) } }
            if (draft.isBlank() && pending.isEmpty()) {
                ComposerRound(if (listening) Icons.Default.MicOff else Icons.Default.Mic, active = listening, onClick = {
                    if (listening) {
                        val heard = speech.stopListening()
                        if (heard.isNotBlank()) scope.launch { send(heard, "voice", speak = true) }
                    } else if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) speech.startListening()
                    else askMic.launch(Manifest.permission.RECORD_AUDIO)
                })
            }
        }
    }
}

/** How the thread works, shown until there is a thread. */
@Composable
private fun IntroCard() {
    val c = MP.colors
    Panel {
        Text("How this works", style = MPType.copyLargeMedium, color = c.ink)
        Gap(8.dp)
        Text("Anything you type goes to your care team, and the plus button sends them a photo, a short video, a voice note or a file. Tap the mic, or one of the quick logs, to tell MedPull how you feel: it logs it for you, answers straight away, and passes anything serious to the team.",
            style = MPType.copy, color = c.body)
    }
}

/** The composer while a voice note records: cancel, the clock, and the stop that attaches it. */
@Composable
private fun RecordingBar(onCancel: () -> Unit, onStop: () -> Unit) {
    val c = MP.colors
    var seconds by remember { mutableStateOf(0) }
    LaunchedEffect(Unit) { while (isActive) { delay(1000); seconds += 1; if (seconds >= 180) { onStop(); break } } }
    Row(Modifier.fillMaxWidth().background(c.panel).padding(horizontal = 8.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onCancel) { Icon(Icons.Default.Close, "Cancel the voice note", tint = c.ink) }
        Row(Modifier.weight(1f).clip(RoundedCornerShape(22.dp)).background(c.soft).padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).clip(RoundedCornerShape(4.dp)).background(c.riskHigh))
            Spacer(Modifier.width(10.dp))
            Text(String.format(Locale.getDefault(), "%d:%02d", seconds / 60, seconds % 60), style = MaterialTheme.typography.bodyLarge, color = c.ink)
            Spacer(Modifier.width(10.dp))
            Text("Recording", style = MaterialTheme.typography.labelMedium, color = c.muted)
        }
        IconButton(onClick = onStop) { Icon(Icons.Default.Stop, "Stop and attach the voice note", tint = c.riskHigh) }
    }
}

/** The patient's words on the sage bubble, everyone else's on the warm grey one; a tail on the bottom corner. */
private fun bubbleShape(mine: Boolean) = RoundedCornerShape(topStart = 26.dp, topEnd = 26.dp,
    bottomStart = if (mine) 26.dp else 6.dp, bottomEnd = if (mine) 6.dp else 26.dp)

@Composable
private fun BubbleText(text: String, mine: Boolean, strong: Boolean = false) {
    val c = MP.colors
    val shape = bubbleShape(mine)
    Box(Modifier.clip(shape).then(if (mine) Modifier.grain().background(BubbleBrush) else Modifier.background(c.panel.copy(alpha = .7f)).background(if (strong) c.fillStrong else c.fill))
        .padding(horizontal = 14.dp, vertical = 10.dp)) {
        Text(text, style = MPType.copyLarge, color = if (mine) Color.White else c.ink)
    }
}

@Composable
private fun TurnBubble(mine: Boolean, text: String) {
    val c = MP.colors
    Column(Modifier.fillMaxWidth().padding(start = if (mine) 48.dp else 0.dp, end = if (mine) 0.dp else 48.dp),
        horizontalAlignment = if (mine) Alignment.End else Alignment.Start, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        BubbleText(text, mine)
        Text(if (mine) "You" else "MedPull", style = MPType.label, color = c.muted)
    }
}

@Composable
private fun Bubble(m: ChatMessage, cache: MediaCache, onOpenTask: (Int) -> Unit) {
    val c = MP.colors
    val mine = m.sender == "patient"
    val who = when {
        mine -> "You" + if (m.channel == "sms") "${DOT}by text" else if (m.channel == "voice") "${DOT}by voice" else ""
        m.sender == "copilot" -> if (m.channel == "sms") "MedPull${DOT}text" else "MedPull"
        m.fromClinician -> m.authorName?.takeIf { it.isNotBlank() } ?: "Care team"
        else -> "Care team"
    }
    Column(Modifier.fillMaxWidth().padding(start = if (mine) 48.dp else 0.dp, end = if (mine) 0.dp else 48.dp),
        horizontalAlignment = if (mine) Alignment.End else Alignment.Start, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        if (m.text.isNotBlank()) BubbleText(m.text, mine, strong = m.sender == "care_team" || m.fromClinician)
        if (m.files.isNotEmpty()) AttachmentStrip(m.files, cache)
        m.action?.takeIf { it.kind == "open_task" && it.taskId != null }?.let { a ->
            PrimaryButton(a.label.ifBlank { "Open" }, modifier = Modifier.widthIn(max = 260.dp)) { onOpenTask(a.taskId!!) }
        }
        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(2.dp),
            itemVerticalAlignment = Alignment.CenterVertically) {
            Text(who, style = MPType.label, color = c.muted)
            if (m.fromClinician) Text("Care team approved", style = MPType.labelMedium, color = c.brandInk,
                modifier = Modifier.clip(CapsuleShape).background(c.brandTint).padding(horizontal = 6.dp, vertical = 2.dp))
            Text("·", style = MPType.label, color = c.muted)
            Text(Dates.relative(m.createdAt) ?: "", style = MPType.label, color = c.muted)
            if (m.deliveryStatus == "failed") Text("·  not delivered by text", style = MPType.label, color = c.riskMed)
        }
    }
}

@Composable
private fun AttachmentStrip(files: List<ChatAttachment>, cache: MediaCache) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        files.forEach { a ->
            when {
                a.isWithdrawn -> Text("${if (a.isImage) "Photo" else "File"} taken back", style = MaterialTheme.typography.labelMedium, color = MP.colors.muted)
                a.isImage -> ImageTile(a, cache)
                a.isVideo || a.isAudio -> MediaTile(a, cache)
                else -> Text("${a.displayName()} · ${a.sizeLabel()}", style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
            }
        }
    }
}

fun ChatAttachment.displayName() = filename ?: if (isImage) "Photo" else if (isVideo) "Video" else if (isAudio) "Voice note" else "File"
fun ChatAttachment.sizeLabel(): String = if (byteSize >= 1_000_000) String.format(Locale.getDefault(), "%.1f MB", byteSize / 1e6) else "${byteSize / 1000} KB"

@Composable
private fun ImageTile(a: ChatAttachment, cache: MediaCache) {
    var file by remember(a.id) { mutableStateOf(cache.cached(a)) }
    LaunchedEffect(a.id) { if (file == null) file = cache.fetch(a) }
    val f = file
    if (f == null) Box(Modifier.size(180.dp, 120.dp).clip(RoundedCornerShape(12.dp)).background(MP.colors.soft))
    else AsyncImage(model = f, contentDescription = a.displayName(), modifier = Modifier.widthIn(max = 260.dp).clip(RoundedCornerShape(12.dp)))
}

@Composable
private fun MediaTile(a: ChatAttachment, cache: MediaCache) {
    val context = LocalContext.current
    var file by remember(a.id) { mutableStateOf(cache.cached(a)) }
    var playing by remember { mutableStateOf(false) }
    LaunchedEffect(a.id) { if (file == null) file = cache.fetch(a) }
    val c = MP.colors
    Row(Modifier.clip(RoundedCornerShape(12.dp)).background(c.soft).clickable(enabled = file != null) { playing = !playing }.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(if (playing) Icons.Default.Stop else Icons.Default.PlayArrow, if (playing) "Stop" else "Play", tint = c.brandInk)
        Spacer(Modifier.width(8.dp))
        Text("${a.displayName()} · ${a.sizeLabel()}", style = MaterialTheme.typography.bodyMedium, color = c.ink)
    }
    val f = file
    if (playing && f != null) Player(f, a.isVideo) { playing = false }
}

@Composable
private fun Player(file: File, video: Boolean, onEnded: () -> Unit) {
    val context = LocalContext.current
    val player = remember(file) { ExoPlayer.Builder(context).build().apply {
        setMediaItem(MediaItem.fromUri(Uri.fromFile(file))); prepare(); playWhenReady = true
    } }
    DisposableEffect(player) {
        val l = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) { if (playbackState == Player.STATE_ENDED) onEnded() }
        }
        player.addListener(l)
        onDispose { player.removeListener(l); player.release() }
    }
    if (video) AndroidView(factory = { ctx -> PlayerView(ctx).apply { this.player = player; useController = true } },
        modifier = Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(12.dp)))
}

/** The care team as overlapping soft discs over the thread, as on the iPhone. */
@Composable
private fun CareHeader(team: List<com.medpull.recovery.core.CareTeamMember>) {
    val c = MP.colors
    if (team.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 10.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy((-10).dp)) {
            team.take(3).forEach { m ->
                Box(Modifier.size(44.dp).clip(CircleShape).background(c.canvas), contentAlignment = Alignment.Center) {
                    Initials(m.name, size = 40.dp, tone = Tone.MISSING, soft = true)
                }
            }
        }
        Text("Your care team", style = MPType.copyMedium, color = c.ink)
        Text(team.joinToString(", ") { it.name }, style = MPType.label, color = c.muted, textAlign = TextAlign.Center)
    }
}

/** A quick log: a small white glass capsule that fills the field. */
@Composable
private fun QuickChip(label: String, onClick: () -> Unit) {
    val c = MP.colors
    Text(label, style = MPType.copyMedium, color = c.ink,
        modifier = Modifier.padding(vertical = 5.dp).glassSurface(CapsuleShape, solid = true).clip(CapsuleShape).clickable(onClick = onClick)
            .defaultMinSize(minHeight = 34.dp).padding(horizontal = 14.dp, vertical = 8.dp))
}

/** The 44pt round button beside the field: a panel disc with a lineStrong edge and a sage glyph; `active` is the risk fill. */
@Composable
private fun ComposerRound(icon: ImageVector, enabled: Boolean = true, active: Boolean = false, onClick: () -> Unit) {
    val c = MP.colors
    Box(Modifier.size(44.dp).clip(CircleShape).background(if (!enabled) c.soft else if (active) c.riskHigh else c.panel)
        .border(1.dp, if (active || !enabled) Color.Transparent else c.lineStrong, CircleShape).clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = if (!enabled) c.muted else if (active) c.panel else c.brandInk, modifier = Modifier.size(20.dp))
    }
}

/** The composer: a capsule field with the send button inside it. */
@Composable
private fun ComposerField(text: String, onChange: (String) -> Unit, placeholder: String, canSend: Boolean, busy: Boolean,
                          modifier: Modifier = Modifier, onSend: () -> Unit) {
    val c = MP.colors
    Row(modifier.defaultMinSize(minHeight = 44.dp).background(c.panel, RoundedCornerShape(22.dp)).border(1.dp, c.lineStrong.copy(alpha = .75f), RoundedCornerShape(22.dp))
        .padding(start = 16.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.Bottom) {
        Box(Modifier.weight(1f).padding(vertical = 8.dp)) {
            if (text.isEmpty()) Text(placeholder, style = MPType.copyLarge, color = c.muted)
            BasicTextField(text, onChange, textStyle = MPType.copyLarge.copy(color = c.ink), maxLines = 5, cursorBrush = SolidColor(c.brand))
        }
        Spacer(Modifier.width(4.dp))
        Box(Modifier.size(36.dp).clip(CircleShape).background(if (canSend) c.action else c.soft).clickable(enabled = canSend && !busy, onClick = onSend), contentAlignment = Alignment.Center) {
            if (busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = c.onAction)
            else Icon(Icons.Default.ArrowUpward, "Send", tint = if (canSend) c.onAction else c.muted, modifier = Modifier.size(18.dp))
        }
    }
}
