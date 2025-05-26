📡 AWS Lambda - CloudWatch Alarm to Slack
이 Lambda 함수는 AWS CloudWatch 경보가 발생했을 때 해당 정보를 Slack 채널로 전송합니다.
메트릭 세부 정보, 인스턴스 이름, 최근 알람 상태 변경 이력까지 포함한 Block Kit 메시지 형식으로 구성됩니다.

✅ 기능 요약
CloudWatch 경보 SNS 메시지를 파싱

관련 메트릭 데이터를 CloudWatch에서 조회

EC2 인스턴스 ID → 이름 태그 변환 (캐시 지원)

알람 상태 변경 이력 3건 조회

Slack Block Kit 메시지로 알림 전송

경보/대시보드 콘솔 바로가기 링크 포함

📦 구성 환경
Python 3.9

AWS Lambda

CloudWatch / EC2 / SNS / Slack Webhook

🔧 환경 변수
변수명	설명
SLACK_WEBHOOK_URL	Slack Webhook URL (앱 설정 후 획득)

🔐 IAM 권한 필요
{
  "Effect": "Allow",
  "Action": [
    "cloudwatch:GetMetricData",
    "cloudwatch:DescribeAlarmHistory",
    "ec2:DescribeInstances"
  ],
  "Resource": "*"
}

🧪 테스트 트리거 예시 (SNS 이벤트)
{
  "Records": [
    {
      "Sns": {
        "Message": "{ CloudWatch Alarm JSON payload }"
      }
    }
  ]
}
📝 주요 포맷 예시 (Slack 출력)
[*ALARM*] `HighCPUAlarm`
*설명:* CPU 사용률이 80% 초과

*CPUUtilization*: `91.7` Percent : `web-server-prod-01`

*최근 알람 이벤트:*
- 2024-05-26T03:12:00 : `Threshold Crossed...`

<경보 바로가기> | <대시보드 바로가기>
🧠 기타 참고
인스턴스 이름은 컨테이너가 살아있는 동안 캐시됩니다.

알람 이력이 없거나 오류 시 _최근 알람 이벤트 없음 또는 조회 실패_ 문구 출력됩니다.

메시지는 Slack Block Kit을 사용하여 깔끔하게 출력됩니다.
