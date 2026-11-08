plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}
android {
    namespace = "app.livingworld.mobile"
    compileSdk = 36
    defaultConfig { minSdk = 24; ndk { abiFilters += listOf("arm64-v8a") }; consumerProguardFiles("consumer-rules.pro") }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_1_8; targetCompatibility = JavaVersion.VERSION_1_8 }
    kotlinOptions { jvmTarget = "1.8" }
}
chaquopy {
    defaultConfig {
        version = "3.13"
        extractPackages("livingworld.infrastructure.persistence.migrations", "jieba")
        buildPython(providers.environmentVariable("DREAMTALK_BUILD_PYTHON").getOrElse("python"))
        pip {
            install("pydantic==2.10.6")
            install(rootProject.file("../../../../../build-tools/wheels/pydantic_core-2.27.2-cp313-cp313-android_24_arm64_v8a.whl").absolutePath)
            install("fastapi==0.115.12")
            install("sqlalchemy==2.0.54")
            install("greenlet==3.1.1")
            install("alembic==1.20.0")
            install("aiosqlite==0.21.0")
            install("uvicorn==0.34.2")
            install("httpx==0.28.1")
            install("pillow==11.0.0")
            install(rootProject.file("../../../../../build-tools/wheels/chaquopy_freetype-2.9.1-1-py3-none-android_24_arm64_v8a.whl").absolutePath)
            install("diskcache==5.6.3")
            install(rootProject.file("../../../../../build-tools/wheels/jieba-0.42.1-py3-none-any.whl").absolutePath)
            install(rootProject.file("../../../../../build-tools/wheels/rpds_py-0.25.1-cp313-cp313-android_24_arm64_v8a.whl").absolutePath)
            install("jsonschema==4.26.0")
            install("referencing==0.37.0")
            install("tinytag==2.2.1")
            install(rootProject.file("../../../../../build-tools/wheels/dreamtalk_core-0.1.0-py3-none-any.whl").absolutePath)
        }
    }
}
dependencies { implementation(project(":tauri-android")); implementation("androidx.appcompat:appcompat:1.7.1") }
