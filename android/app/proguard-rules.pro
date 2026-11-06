# kotlinx.serialization: keep the generated serializers and the model fields.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** { kotlinx.serialization.KSerializer serializer(...); }
-keep,includedescriptorclasses class com.medpull.recovery.**$$serializer { *; }
-keepclassmembers class com.medpull.recovery.** { *** Companion; }
-keepclasseswithmembers class com.medpull.recovery.** { kotlinx.serialization.KSerializer serializer(...); }
# Retrofit
-keepattributes Signature, Exceptions
-dontwarn org.codehaus.mojo.animal_sniffer.*
-dontwarn javax.annotation.**
