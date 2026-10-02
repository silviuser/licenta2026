plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.hrhelper"
version = "0.1.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

extra["testcontainersVersion"] = "1.21.3"

dependencies {
    // Web + persistence + validation + security
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    // WebClient (reactive) for the NLP client (D8)
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    // DB driver + migrations
    runtimeOnly("org.postgresql:postgresql")
    implementation("org.flywaydb:flyway-core")
    implementation("org.flywaydb:flyway-database-postgresql")

    // JWT (D5)
    implementation("io.jsonwebtoken:jjwt-api:0.12.6")
    runtimeOnly("io.jsonwebtoken:jjwt-impl:0.12.6")
    runtimeOnly("io.jsonwebtoken:jjwt-jackson:0.12.6")

    // OpenAPI / Swagger UI
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.6.0")

    // Tests
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.awaitility:awaitility")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

dependencyManagement {
    imports {
        mavenBom("org.testcontainers:testcontainers-bom:${property("testcontainersVersion")}")
    }
}

tasks.withType<Test> {
    useJUnitPlatform()

    // Testcontainers + Docker Desktop on Windows: the bundled docker-java negotiates
    // an API version below the engine's minimum (1.40), which Docker Desktop's named-pipe
    // proxy rejects with HTTP 400. Pin a supported API version and the Linux engine pipe
    // so the test JVM connects reliably regardless of the shell environment.
    environment("DOCKER_API_VERSION", "1.43")
    if (System.getProperty("os.name").startsWith("Windows")) {
        environment("DOCKER_HOST", "npipe:////./pipe/dockerDesktopLinuxEngine")
    }
}
