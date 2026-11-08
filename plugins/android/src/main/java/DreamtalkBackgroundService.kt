package app.livingworld.mobile
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper

/** User-started world session, stoppable through its visible status notification. */
class DreamtalkBackgroundService: Service() {
    private val handler = Handler(Looper.getMainLooper())
    private var checking = false
    private val tick = object: Runnable {
        override fun run() {
            if (!CoreRuntime.enabled() || !CoreRuntime.notificationsAllowed()) {
                CoreRuntime.stopBackground(); return
            }
            if (!checking) {
                checking = true
                CoreRuntime.worker.execute {
                    try {
                        CoreRuntime.dispatch("connection")
                        CoreRuntime.dispatch("background_tick")
                    } catch (_: Exception) { CoreRuntime.failure = "mobile_background_check_failed" }
                    finally { handler.post { checking = false } }
                }
            }
            handler.postDelayed(this, 30000)
        }
    }
    override fun onCreate() {
        super.onCreate()
        CoreRuntime.initialize(this)
        CoreRuntime.channels()
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop" || !CoreRuntime.enabled() || !CoreRuntime.notificationsAllowed()) {
            CoreRuntime.stopBackground(); stopSelf(); return START_NOT_STICKY
        }
        try {
            if (Build.VERSION.SDK_INT >= 34) startForeground(7001, CoreRuntime.runningNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
            else startForeground(7001, CoreRuntime.runningNotification())
        } catch (_: Exception) {
            CoreRuntime.failure = "mobile_background_start_failed"
            CoreRuntime.stopBackground(); stopSelf(); return START_NOT_STICKY
        }
        CoreRuntime.serviceRunning = true
        CoreRuntime.failure = null
        CoreRuntime.syncVisibility()
        handler.removeCallbacks(tick)
        handler.post(tick)
        return START_STICKY
    }
    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        CoreRuntime.serviceRunning = false
        CoreRuntime.syncVisibility()
        super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
class DreamtalkBootReceiver: BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val preferences = context.getSharedPreferences("dreamtalk-background", 0)
        if (!preferences.getBoolean("enabled", false) || !preferences.getBoolean("start_on_boot", false)) return
        CoreRuntime.initialize(context)
        if (CoreRuntime.enabled() && CoreRuntime.startOnBoot() && CoreRuntime.notificationsAllowed()) {
            try { CoreRuntime.startService() }
            catch (_: Exception) { CoreRuntime.failure = "mobile_background_start_failed" }
        }
    }
}
