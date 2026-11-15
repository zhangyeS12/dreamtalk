package app.livingworld.mobile

import android.content.Context
import androidx.annotation.Keep
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import java.io.File
import java.nio.LongBuffer
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

/** Fixed product retrieval resource. No model URL, credentials or UI deployment path. */
@Keep object SemanticRecall {
    private const val HASH = "1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38"
    private var session: OrtSession? = null
    private val environment by lazy { OrtEnvironment.getEnvironment() }

    private fun model(context: Context): OrtSession {
        session?.let { return it }
        val directory = File(context.noBackupFilesDir, "semantic-model").apply { mkdirs() }
        val target = File(directory, "$HASH.onnx")
        if (!target.isFile || digest(target) != HASH) {
            val staging = File(directory, "$HASH.pending")
            try {
                context.assets.open("semantic-model/model_optimized.onnx").use { input ->
                    staging.outputStream().use { output -> input.copyTo(output) }
                }
                check(digest(staging) == HASH) { "mobile_recall_resource_invalid" }
                check(staging.renameTo(target)) { "mobile_recall_resource_copy_failed" }
            } finally { staging.delete() }
        }
        val options = OrtSession.SessionOptions()
        try {
            options.setIntraOpNumThreads(2)
            options.setInterOpNumThreads(2)
            options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
            return environment.createSession(target.absolutePath, options).also { session = it }
        } finally { options.close() }
    }

    private fun digest(file: File): String {
        val hash = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(128 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                hash.update(buffer, 0, n)
            }
        }
        return hash.digest().joinToString("") { "%02x".format(it) }
    }

    @Synchronized fun embed(context: Context, payload: String): String {
        val raw = JSONObject(NativeBounds().recallTokens(payload))
        val ids = raw.getJSONArray("ids")
        val rows = ids.length()
        require(rows in 1..16) { "mobile_recall_batch_invalid" }
        val length = ids.getJSONArray(0).length()
        require(length in 2..512) { "mobile_recall_sequence_invalid" }
        val tensors = linkedMapOf<String, OnnxTensor>()
        try {
            for ((key, name) in listOf("ids" to "input_ids", "mask" to "attention_mask", "types" to "token_type_ids")) {
                val array = raw.getJSONArray(key)
                require(array.length() == rows)
                val values = LongArray(rows * length)
                for (row in 0 until rows) {
                    val sequence = array.getJSONArray(row)
                    require(sequence.length() == length)
                    for (col in 0 until length) values[row * length + col] = sequence.getLong(col)
                }
                tensors[name] = OnnxTensor.createTensor(environment, LongBuffer.wrap(values),
                    longArrayOf(rows.toLong(), length.toLong()))
            }
            model(context).run(tensors).use { output ->
                val tensor = output.get(0) as OnnxTensor
                val shape = (tensor.info as TensorInfo).shape
                require(shape.size in 2..3 && shape[0] == rows.toLong() && shape.last() == 512L) {
                    "mobile_recall_shape_invalid"
                }
                val stride = if (shape.size == 3) shape[1].toInt() * 512 else 512
                val buffer = tensor.floatBuffer
                val result = JSONArray()
                for (row in 0 until rows) {
                    val vector = JSONArray()
                    for (col in 0 until 512) {
                        val value = buffer.get(row * stride + col)
                        require(value.isFinite()) { "mobile_recall_value_invalid" }
                        vector.put(value.toDouble())
                    }
                    result.put(vector)
                }
                return result.toString()
            }
        } finally { tensors.values.forEach { it.close() } }
    }
}
