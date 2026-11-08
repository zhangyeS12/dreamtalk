package app.livingworld.mobile

import android.app.*
import android.content.*
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.annotation.Keep
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.security.KeyStore
import java.util.concurrent.Executors
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

@Keep class NativeBounds { external fun tokenUpperBound(payload: String): Long }

/** Application context only: neither Activity nor WebView owns the running Core. */
@Keep object CoreRuntime {
    lateinit var context: Context
        private set
    val worker = Executors.newSingleThreadExecutor()
    @Volatile var foreground = false
    @Volatile var serviceRunning = false
    @Volatile var failure: String? = null
    @Volatile var notificationTarget: JSONObject? = null
    private val preferences get() = context.getSharedPreferences("dreamtalk-api", 0)
    private val background get() = context.getSharedPreferences("dreamtalk-background", 0)
    @Synchronized fun initialize(value: Context) {
        if (!::context.isInitialized) {
            context = value.applicationContext
            System.loadLibrary("dreamtalk_mobile")
        }
    }
    fun dataDirectory(): String = java.io.File(context.filesDir.canonicalFile, "dreamtalk").absolutePath
    fun isForeground(): Boolean = foreground
    fun isBackgroundRunning(): Boolean = serviceRunning
    fun tokenUpperBound(payload: String): Long = NativeBounds().tokenUpperBound(payload)
    private fun encryptionKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "dreamtalk.api.v1"
        if (!store.containsAlias(alias)) {
            KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
                init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true).build())
            }.generateKey()
        }
        return store.getKey(alias, null) as SecretKey
    }
    @Synchronized fun secureRead(): String {
        val encoded = preferences.getString("encrypted-config", null) ?: return "{}"
        val parts = encoded.split(":")
        check(parts.size == 2) { "mobile_secure_store" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, encryptionKey(), GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)))
        return String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), Charsets.UTF_8)
    }
    @Synchronized fun secureWrite(value: String) {
        check(value.toByteArray(Charsets.UTF_8).size <= 524288) { "mobile_secure_store" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, encryptionKey())
        val encoded = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(cipher.doFinal(value.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
        check(preferences.edit().putString("encrypted-config", encoded).commit()) { "mobile_secure_store" }
    }
    fun dispatch(operation: String, payload: String = "{}"): String {
        synchronized(Python::class.java) { if (!Python.isStarted()) Python.start(AndroidPlatform(context)) }
        return Python.getInstance().getModule("livingworld.bootstrap.mobile_host").callAttr("dispatch", operation, payload, this).toString()
    }
    fun syncVisibility() {
        worker.execute { try { if (Python.isStarted()) dispatch("visibility") } catch (_: Exception) { failure = "mobile_visibility_failed" } }
    }
    fun copyDiagnostic(value: String) {
        Handler(Looper.getMainLooper()).post {
            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("dreamtalk 诊断", value))
        }
    }
    fun enabled(): Boolean = background.getBoolean("enabled", false)
    fun startOnBoot(): Boolean = background.getBoolean("start_on_boot", false)
    fun notificationsAllowed(): Boolean {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        return manager.areNotificationsEnabled() && (Build.VERSION.SDK_INT < 26 || manager.getNotificationChannel("dreamtalk-contacts")?.importance != NotificationManager.IMPORTANCE_NONE)
    }
    fun channels() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(NotificationChannel("dreamtalk-running", "后台运行状态", NotificationManager.IMPORTANCE_LOW))
            manager.createNotificationChannel(NotificationChannel("dreamtalk-contacts", "角色主动联系", NotificationManager.IMPORTANCE_DEFAULT))
        }
    }
    fun status(): JSONObject {
        val power = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        return JSONObject().put("enabled", enabled()).put("running", serviceRunning)
            .put("start_on_boot", startOnBoot()).put("notifications_allowed", notificationsAllowed())
            .put("battery_unrestricted", power.isIgnoringBatteryOptimizations(context.packageName))
            .put("problem", failure ?: JSONObject.NULL)
    }
    fun configure(value: JSONObject) {
        val enabled = value.getBoolean("enabled")
        val boot = value.optBoolean("start_on_boot", false)
        if (enabled) {
            check(value.optBoolean("consent")) { "mobile_background_consent" }
            channels()
            check(notificationsAllowed()) { "mobile_notification_permission" }
            // Establish the cursor before background generation becomes eligible.
            dispatch("notification_baseline")
            check(background.edit().putBoolean("enabled", true).putBoolean("start_on_boot", boot).commit())
            try { startService() }
            catch (_: Exception) {
                background.edit().putBoolean("enabled", false).commit()
                failure = "mobile_background_start_failed"
                throw IllegalStateException("mobile_background_start_failed")
            }
        } else stopBackground()
    }
    fun startService() {
        val intent = Intent(context, DreamtalkBackgroundService::class.java)
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent) else context.startService(intent)
    }
    fun stopBackground() {
        background.edit().putBoolean("enabled", false).putBoolean("start_on_boot", false).commit()
        serviceRunning = false
        context.stopService(Intent(context, DreamtalkBackgroundService::class.java))
        syncVisibility()
    }
    fun launchIntent(): Intent = context.packageManager.getLaunchIntentForPackage(context.packageName)!!
        .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
    fun captureTarget(intent: Intent?) {
        val raw = intent?.getStringExtra("dreamtalk-contact") ?: return
        intent.removeExtra("dreamtalk-contact")
        try {
            val target = JSONObject(raw)
            for (key in listOf("world_id", "conversation_id", "player_id")) java.util.UUID.fromString(target.getString(key))
            notificationTarget = target
        } catch (_: Exception) { notificationTarget = null }
    }
    fun runningNotification(): Notification {
        val open = PendingIntent.getActivity(context, 0, launchIntent(), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(context, 1, Intent(context, DreamtalkBackgroundService::class.java).setAction("stop"), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(context, "dreamtalk-running") else Notification.Builder(context).setPriority(Notification.PRIORITY_LOW)
        return builder.setSmallIcon(R.drawable.ic_dreamtalk_notification).setContentTitle("dreamtalk 后台运行中")
            .setContentText("已开启的角色活动与主动联系可以继续；可能产生 API 费用")
            .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(Notification.Action.Builder(null, "停止后台运行", stop).build()).build()
    }
    fun postContactNotification(raw: String): Boolean {
        if (!serviceRunning || !enabled() || !notificationsAllowed()) return false
        val item = JSONObject(raw)
        val id = item.getString("id")
        val intent = launchIntent().setData(Uri.parse("dreamtalk://contact/" + id)).putExtra("dreamtalk-contact", raw)
        val open = PendingIntent.getActivity(context, id.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(context, "dreamtalk-contacts") else Notification.Builder(context)
        // No private transcript body is sent to the lock screen.
        val notification = builder.setSmallIcon(R.drawable.ic_dreamtalk_notification)
            .setContentTitle(item.getString("title")).setContentText("给你发来一条新消息")
            .setContentIntent(open).setAutoCancel(true).setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_MESSAGE).setVisibility(Notification.VISIBILITY_PRIVATE).build()
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify("contact:" + id, 2, notification)
        return true
    }
}
