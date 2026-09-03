ARG JENKINS_BASE_IMAGE=jenkins/jenkins:2.568.2-jdk21
FROM ${JENKINS_BASE_IMAGE}

ARG TRIVY_VERSION=0.74.0

USER root

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg tar; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg \
      -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    . /etc/os-release; \
    printf '%s\n' \
      'Types: deb' \
      'URIs: https://download.docker.com/linux/debian' \
      "Suites: ${VERSION_CODENAME}" \
      'Components: stable' \
      "Architectures: $(dpkg --print-architecture)" \
      'Signed-By: /etc/apt/keyrings/docker.asc' \
      > /etc/apt/sources.list.d/docker.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      docker-ce-cli \
      docker-buildx-plugin \
      docker-compose-plugin; \
    curl -fsSLo "/tmp/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" \
      "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"; \
    curl -fsSLo /tmp/trivy_checksums.txt \
      "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_checksums.txt"; \
    grep " trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz$" \
      /tmp/trivy_checksums.txt \
      > /tmp/trivy_checksum.txt; \
    cd /tmp; \
    sha256sum -c trivy_checksum.txt; \
    tar -xzf "trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" \
      -C /usr/local/bin trivy; \
    chmod 0755 /usr/local/bin/trivy; \
    trivy --version; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/* \
      "/tmp/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" \
      /tmp/trivy_checksums.txt \
      /tmp/trivy_checksum.txt

COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt

RUN jenkins-plugin-cli -f /usr/share/jenkins/ref/plugins.txt

COPY --chown=jenkins:jenkins init.groovy.d/ \
  /usr/share/jenkins/ref/init.groovy.d/

RUN git config --system http.version HTTP/1.1

USER jenkins
