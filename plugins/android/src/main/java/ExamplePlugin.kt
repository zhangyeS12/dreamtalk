package app.livingworld.mobile
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import app.tauri.annotation.*
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import app.tauri.plugin.Invoke
import app.tauri.PermissionState
import androidx.activity.result.ActivityResult
import org.json.JSONObject
import java.io.File
import java.util.UUID

@InvokeArg class CallArgs { var operation: String = ""; var payload: String = "{}" }
@TauriPlugin(permissions = [Permission(strings = ["android.permission.POST_NOTIFICATIONS"], alias = "notifications")])
class ExamplePlugin(private val activity: Activity): Plugin(activity) {
    init { CoreRuntime.initialize(activity); CoreRuntime.foreground = true; CoreRuntime.captureTarget(activity.intent) }
    override fun onStop(activity: androidx.appcompat.app.AppCompatActivity) { CoreRuntime.foreground = false; CoreRuntime.syncVisibility() }
    override fun onResume(activity: androidx.appcompat.app.AppCompatActivity) {
        CoreRuntime.foreground = true
        CoreRuntime.captureTarget(activity.intent)
        if (CoreRuntime.enabled() && !CoreRuntime.serviceRunning && CoreRuntime.notificationsAllowed()) {
            try { CoreRuntime.startService() } catch (_: Exception) { CoreRuntime.failure = "mobile_background_start_failed" }
        }
        CoreRuntime.syncVisibility()
    }
    override fun onNewIntent(intent: Intent) { CoreRuntime.captureTarget(intent) }
    private fun resolve(invoke: Invoke, value: Any?) { val result = JSObject(); result.put("result", value ?: JSONObject.NULL); invoke.resolve(result) }
    private fun transferDirectory(): File = File(activity.filesDir, "dreamtalk-transfers").apply { mkdirs() }
    @Command fun call(invoke: Invoke) {
        val args = invoke.parseArgs(CallArgs::class.java)
        if (args.operation.length > 64 || args.payload.toByteArray().size > 65536) { invoke.reject("mobile_invalid_request"); return }
        when (args.operation) {
            "request_notifications" -> {
                CoreRuntime.channels()
                if (Build.VERSION.SDK_INT >= 33 && getPermissionState("notifications") != PermissionState.GRANTED) requestPermissionForAlias("notifications", invoke, "notificationPermission")
                else resolve(invoke, CoreRuntime.notificationsAllowed())
                return
            }
            "notification_settings", "battery_settings" -> {
                activity.runOnUiThread {
                    try {
                        val intent = if (args.operation == "notification_settings" && Build.VERSION.SDK_INT >= 26) Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, activity.packageName)
                        else Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + activity.packageName))
                        activity.startActivity(intent); resolve(invoke, true)
                    } catch (_: Exception) { invoke.reject("mobile_settings_unavailable") }
                }
                return
            }
            "import_document" -> {
                activity.runOnUiThread { startActivityForResult(invoke, Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), "importDocument") }
                return
            }
            "export_document" -> {
                val path = File(JSONObject(args.payload).getString("path"))
                if (path.canonicalFile.parentFile != transferDirectory().canonicalFile || !path.isFile) { invoke.reject("mobile_invalid"); return }
                activity.runOnUiThread { startActivityForResult(invoke, Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE, JSONObject(args.payload).optString("filename", "dreamtalk.dreamsave").take(100)), "exportDocument") }
                return
            }
        }
        CoreRuntime.worker.execute {
            try {
                when (args.operation) {
                    "background_status" -> resolve(invoke, CoreRuntime.status())
                    "configure_background" -> { CoreRuntime.configure(JSONObject(args.payload)); resolve(invoke, CoreRuntime.status()) }
                    "notification_target" -> { val target = CoreRuntime.notificationTarget; CoreRuntime.notificationTarget = null; resolve(invoke, target) }
                    "create_transfer" -> {
                        val extension = JSONObject(args.payload).getString("extension")
                        check(extension in listOf("voicecard", "dreamsave")) { "mobile_invalid" }
                        val target = File(transferDirectory(), UUID.randomUUID().toString() + "." + extension)
                        check(target.createNewFile()) { "mobile_invalid" }; resolve(invoke, target.absolutePath)
                    }
                    "append_transfer", "discard_transfer" -> {
                        val value = JSONObject(args.payload)
                        val target = File(value.getString("path"))
                        check(target.canonicalFile.parentFile == transferDirectory().canonicalFile && target.isFile) { "mobile_invalid" }
                        if (args.operation == "discard_transfer") target.delete()
                        else {
                            val data = android.util.Base64.decode(value.getString("data"), android.util.Base64.DEFAULT)
                            check(data.size <= 32768 && target.length() + data.size <= 16L * 1024 * 1024) { "mobile_invalid" }
                            target.appendBytes(data)
                        }
                        resolve(invoke, true)
                    }
                    "app_info" -> resolve(invoke, JSONObject().put("platform", "Android").put("version", activity.packageManager.getPackageInfo(activity.packageName, 0).versionName).put("android", Build.VERSION.RELEASE).put("background", CoreRuntime.status()))
                    else -> invoke.resolve(JSObject(CoreRuntime.dispatch(args.operation, args.payload)))
                }
            } catch (failure: Exception) {
                val description = failure.message ?: ""
                val safe = listOf("mobile_busy", "mobile_invalid", "mobile_secure_store", "mobile_core_start_failed", "mobile_background_consent", "mobile_notification_permission", "mobile_background_start_failed", "model_update_new_secret_required").firstOrNull { description.contains(it) }
                    ?: listOf("save_busy", "save_tasks_running", "save_slot_changed", "save_slot_empty", "save_snapshot_damaged", "save_import_invalid", "save_newer_application_required", "save_recovery_required", "save_restore_interrupted", "save_startup_backup_failed").firstOrNull { description.contains(it) } ?: "mobile_operation_failed"
                // Code-only diagnostics: exception text may contain credentials or inputs.
                val diagnostic = JSONObject().put("app", "dreamtalk").put("native_error", failure.javaClass.simpleName).put("code", safe)
                val frames = org.json.JSONArray()
                failure.stackTrace.take(24).forEach { frame -> frames.put(JSONObject().put("file", frame.fileName?.substringAfterLast('/')?.substringAfterLast('\\') ?: "unknown").put("line", frame.lineNumber).put("function", frame.methodName)) }
                diagnostic.put("frames", frames)
                CoreRuntime.failure = safe
                if (args.operation == "copy_diagnostics") { CoreRuntime.copyDiagnostic(diagnostic.toString()); resolve(invoke, true) }
                else invoke.reject(safe)
            }
        }
    }
    @PermissionCallback private fun notificationPermission(invoke: Invoke) { resolve(invoke, CoreRuntime.notificationsAllowed()) }
    @ActivityCallback private fun importDocument(invoke: Invoke, result: ActivityResult) {
        val uri = result.data?.data
        if (result.resultCode != Activity.RESULT_OK || uri == null) { resolve(invoke, null); return }
        CoreRuntime.worker.execute {
            val target = File(transferDirectory(), UUID.randomUUID().toString() + ".dreamsave")
            try {
                activity.contentResolver.openInputStream(uri)!!.use { input -> target.outputStream().use { output ->
                    val buffer = ByteArray(65536); var total = 0L
                    while (true) { val count = input.read(buffer); if (count < 0) break; total += count; check(total <= 4L * 1024 * 1024 * 1024); output.write(buffer, 0, count) }
                } }
                resolve(invoke, target.absolutePath)
            } catch (_: Exception) { target.delete(); invoke.reject("save_import_invalid") }
        }
    }
    @ActivityCallback private fun exportDocument(invoke: Invoke, result: ActivityResult) {
        val uri = result.data?.data
        val args = invoke.parseArgs(CallArgs::class.java)
        val source = File(JSONObject(args.payload).getString("path"))
        if (result.resultCode != Activity.RESULT_OK || uri == null) { source.delete(); resolve(invoke, false); return }
        CoreRuntime.worker.execute {
            try {
                check(source.canonicalFile.parentFile == transferDirectory().canonicalFile)
                activity.contentResolver.openOutputStream(uri, "w")!!.use { output -> source.inputStream().use { it.copyTo(output) } }
                resolve(invoke, true)
            } catch (_: Exception) { invoke.reject("save_export_target_invalid") }
            finally { source.delete() }
        }
    }
}
