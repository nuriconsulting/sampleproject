# 🚨 AWS Lambda: CloudWatch Alarm → Slack Webhook

CloudWatch 경보가 발생했을 때 Slack 채널로 실시간 메시지를 전송하는 AWS Lambda 함수입니다.  
경보 메트릭, 인스턴스 이름, 단위, 최근 이벤트 이력 등을 Slack Block Kit 포맷으로 구성해 알림을 제공합니다.

---

## 📌 기능 요약

- CloudWatch 경보 SNS 메시지 수신 및 파싱
- 경보에 포함된 메트릭의 실시간 데이터 조회
- EC2 InstanceId → Name 태그 변환 (Lambda 컨테이너 내 캐시 적용)
- 최근 알람 상태 변경 이력(최대 3건) 출력
- Slack Block Kit 메시지 형식으로 전송
- AWS 콘솔 링크(경보/대시보드) 포함

---

## ⚙️ 환경 변수

| 변수명              | 설명                           |
|---------------------|--------------------------------|
| `SLACK_WEBHOOK_URL` | Slack 앱의 수신용 Webhook URL |

---

## 🔐 필요한 IAM 권한

```json
{
  "Effect": "Allow",
  "Action": [
    "cloudwatch:GetMetricData",
    "cloudwatch:DescribeAlarmHistory",
    "ec2:DescribeInstances"
  ],
  "Resource": "*"
}
```

## 📤 메시지 출력 예시 (Slack)
[*ALARM*] `HighCPUUtilizationAlarm`

*설명:* EC2 인스턴스의 CPU 사용률이 기준치를 초과했습니다.

*CPUUtilization*: `91.3` Percent : `web-server-prod-01`

*최근 알람 이벤트:*
- 2024-05-27T03:12:00+09:00 : `Threshold Crossed: 1 datapoint (91.3) was above threshold (80.0)`
- ...

<경보 바로가기> | <대시보드 바로가기>


## 🚀 배포 방법
이 코드를 Lambda 함수에 업로드

트리거로 SNS Topic을 연결

환경 변수 SLACK_WEBHOOK_URL 설정

위 IAM 정책이 포함된 역할(Role)을 할당

## 📂 파일 구조
.
├── lambda_function.py  # Lambda 함수 본문
├── README.md           # 이 설명서


## 🧠 기타 구현 사항
instance_name_cache를 통해 EC2 이름 조회 결과 캐싱

Slack 메시지 최대 길이 제한(2,000자) 대응

오류 시 _최근 알람 이벤트 없음 또는 조회 실패_ 문구 출력

## 📝 라이선스
MIT License



