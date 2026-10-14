FROM apache/spark:4.1.2-python3

RUN curl -fsSL https://repo1.maven.org/maven2/org/apache/ivy/ivy/2.5.3/ivy-2.5.3.jar \
    -o /tmp/ivy.jar

COPY docker/base/ivy.xml /tmp/ivy.xml

RUN java -Divy.cache.dir=/tmp -Divy.home=/tmp -jar /tmp/ivy.jar \
    -ivy /tmp/ivy.xml \
    -retrieve "/opt/spark/jars/[artifact]-[revision](-[classifier]).[ext]"

RUN rm /tmp/ivy.jar

USER root

RUN pip install --no-cache-dir \
    numpy==2.2.6 pandas==2.3.3 typing_extensions==4.16.0 PyYAML==6.0.3 fsspec>=2022.11.0 s3fs>=2022.11.0

USER spark
