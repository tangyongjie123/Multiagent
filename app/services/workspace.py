"""隔离的生成工程工作区。"""

from __future__ import annotations

from app.agents.schemas import GeneratedFile
from app.core.config import PROJECT_ROOT

POM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>generated-service</artifactId>
    <version>0.1.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.6.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""

APPLICATION_YML = """\
spring:
  application:
    name: generated-service
  profiles:
    active: ${SPRING_PROFILES_ACTIVE:demo}
"""

APPLICATION_DEMO_YML = """\
spring:
  datasource:
    url: jdbc:h2:mem:multiagent;DB_CLOSE_DELAY=-1
    username: sa
    password:
    driver-class-name: org.h2.Driver
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false

server:
  port: ${SERVER_PORT:8080}
"""


class WorkspaceError(ValueError):
    """生成文件路径或大小不符合约束。"""


class WorkspaceManager:
    """管理一次运行的隔离生成目录。"""

    def __init__(self, run_id: str) -> None:
        self.root = (PROJECT_ROOT / "workspaces" / run_id).resolve()
        self.artifact_dir = self.root / "artifacts"

    def initialize(self) -> None:
        """创建目录并写入固定 Spring Boot 骨架。"""

        self.root.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._write_text("pom.xml", POM_XML)
        self._write_text("src/main/resources/application.yml", APPLICATION_YML)
        self._write_text(
            "src/main/resources/application-demo.yml",
            APPLICATION_DEMO_YML,
        )

    def write_application(self, package_name: str) -> str:
        """按架构包名写入 Spring Boot 启动类。"""

        if not package_name or any(
            not part.isidentifier() for part in package_name.split(".")
        ):
            raise WorkspaceError(f"非法 Java 包名: {package_name}")
        package_path = package_name.replace(".", "/")
        relative_path = f"src/main/java/{package_path}/MultiAgentApplication.java"
        source = f"""\
package {package_name};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiAgentApplication {{
    public static void main(String[] args) {{
        SpringApplication.run(MultiAgentApplication.class, args);
    }}
}}
"""
        self._write_text(relative_path, source)
        return relative_path

    def write_generated_files(
        self,
        files: list[GeneratedFile],
        *,
        required_prefix: str,
    ) -> list[str]:
        """校验并写入 Agent 生成的文件。"""

        if not files:
            raise WorkspaceError("Agent 未生成任何文件")

        written: list[str] = []
        total_bytes = 0
        for generated in files:
            normalized = generated.path.replace("\\", "/").lstrip("./")
            if not normalized.startswith(required_prefix):
                raise WorkspaceError(
                    f"文件路径不在允许目录 {required_prefix}: {normalized}"
                )
            payload = generated.content.encode("utf-8")
            total_bytes += len(payload)
            if total_bytes > 1_000_000:
                raise WorkspaceError("生成文件总大小超过 1 MB")
            self._write_text(normalized, generated.content)
            written.append(normalized)
            if len(written) > 40:
                raise WorkspaceError("生成文件数量超过 40")
        return written

    def write_artifact(self, name: str, content: str) -> str:
        """把 Agent 结构化结果保存到工作区。"""

        relative_path = f"artifacts/{name}"
        self._write_text(relative_path, content)
        return str((self.root / relative_path).resolve())

    def write_delivery_files(
        self,
        *,
        readme: str,
        user_manual: str,
        openapi_yaml: str,
    ) -> list[str]:
        """写入 Doc Agent 的最终交付文档。"""

        files = {
            "README.md": readme,
            "docs/USER_MANUAL.md": user_manual,
            "openapi.yaml": openapi_yaml,
        }
        for relative_path, content in files.items():
            self._write_text(relative_path, content)
        return list(files)

    def read_java_sources(self, *, tests: bool = False) -> dict[str, str]:
        """读取生成的生产或测试 Java 源码。"""

        source_root = (
            self.root / "src/test/java"
            if tests
            else self.root / "src/main/java"
        )
        if not source_root.exists():
            return {}
        sources: dict[str, str] = {}
        for path in sorted(source_root.rglob("*.java")):
            relative_path = path.relative_to(self.root).as_posix()
            sources[relative_path] = path.read_text(encoding="utf-8")
        return sources

    def _write_text(self, relative_path: str, content: str) -> None:
        target = (self.root / relative_path).resolve()
        if self.root != target and self.root not in target.parents:
            raise WorkspaceError(f"拒绝写入工作区外路径: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
