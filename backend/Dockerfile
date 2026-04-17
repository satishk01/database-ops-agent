# Lambda container image with response streaming support
FROM public.ecr.aws/lambda/python:3.12

# Install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Download RDS CA bundle for SSL connections to Aurora
RUN curl -sS -o ${LAMBDA_TASK_ROOT}/rds-global-bundle.pem \
    https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

# Copy application code
COPY app/ ${LAMBDA_TASK_ROOT}/app/
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/

# Enable Lambda response streaming
ENV AWS_LWA_INVOKE_MODE=response_stream

CMD ["lambda_handler.handler"]
