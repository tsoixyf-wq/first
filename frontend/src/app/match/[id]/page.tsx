"use client";

import { useParams, useRouter } from "next/navigation";
import {
  Card,
  Col,
  Descriptions,
  Row,
  Tag,
  Progress,
  List,
  Alert,
  Typography,
  Divider,
  Button,
  Space,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  BulbOutlined,
  ArrowLeftOutlined,
} from "@ant-design/icons";
import { ChartCard, ScoreTag, ConfirmButton, ErrorState, PageHeader } from "@/components";
import useApi from "@/hooks/useApi";
import { getMatchResult, deleteMatchResult } from "@/lib/api";
import type { MatchResult } from "@/lib/types";

const { Title, Paragraph, Text } = Typography;

export default function MatchDetailPage() {
  const params = useParams();
  const router = useRouter();

  const { data: match, loading, error, refresh } = useApi<MatchResult>(
    () => getMatchResult(params.id as string)
  );

  if (error) {
    return <ErrorState message={error} onRetry={refresh} />;
  }

  if (!match && !loading) return null;

  async function handleDelete() {
    if (!match) return;
    try {
      await deleteMatchResult(match.id);
      message.success("删除成功");
      router.push("/reports");
    } catch (e: any) {
      message.error(`删除失败: ${e?.response?.data?.detail || e.message}`);
    }
  }

  const radarOption = {
    radar: {
      indicator: [
        { name: "学历匹配", max: 10 },
        { name: "技能匹配", max: 10 },
        { name: "经验匹配", max: 10 },
        { name: "证书匹配", max: 10 },
        { name: "语言能力", max: 10 },
        { name: "地点匹配", max: 10 },
        { name: "综合得分", max: 10 },
      ],
      center: ["50%", "55%"],
      radius: "65%",
      shape: "polygon",
      splitNumber: 5,
      axisName: {
        color: "#8c8c8c",
        fontSize: 12,
      },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: [
              match?.dimension_scores.education ?? 0,
              match?.dimension_scores.skills ?? 0,
              match?.dimension_scores.experience ?? 0,
              match?.dimension_scores.certifications ?? 0,
              match?.dimension_scores.languages ?? 0,
              match?.dimension_scores.location ?? 0,
              match?.dimension_scores.overall ?? 0,
            ],
            name: "匹配度",
            areaStyle: { opacity: 0.3 },
          },
        ],
        itemStyle: { color: "#1677ff" },
      },
    ],
  };

  const scoreColor =
    (match?.overall_score ?? 0) >= 8
      ? "#52c41a"
      : (match?.overall_score ?? 0) >= 6
        ? "#1677ff"
        : (match?.overall_score ?? 0) >= 4
          ? "#faad14"
          : "#f5222d";

  return (
    <div>
      <PageHeader
        title="匹配详情"
        extra={
          <Space>
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => router.push("/reports")}
            >
              返回列表
            </Button>
            <ConfirmButton
              type="default"
              danger
              title="确认删除"
              content="删除后无法恢复，确定要删除这条匹配报告吗？"
              onConfirm={handleDelete}
            >
              删除
            </ConfirmButton>
          </Space>
        }
      />

      {match?.is_hard_pass && (
        <Alert
          message="硬性条件不满足"
          description="未通过"
          type="error"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      <Row gutter={24}>
        <Col xs={24} md={8}>
          <Card>
            <div style={{ textAlign: "center" }}>
              <Title level={5}>综合匹配度</Title>
              <Progress
                type="dashboard"
                percent={(match?.overall_score ?? 0) * 10}
                format={() => (
                  <span
                    style={{
                      fontSize: 36,
                      fontWeight: 700,
                      color: scoreColor,
                    }}
                  >
                    {match?.overall_score ?? "-"}
                  </span>
                )}
                strokeColor={scoreColor}
                size={180}
              />
              <Text type="secondary">满分 10 分</Text>
            </div>
            <Divider />
            <Descriptions column={1} size="small">
              <Descriptions.Item label="规则匹配">
                {match?.rule_score?.toFixed(1) ?? "-"}
              </Descriptions.Item>
              <Descriptions.Item label="TF-IDF">
                {match?.tfidf_score?.toFixed(1) ?? "-"}
              </Descriptions.Item>
              <Descriptions.Item label="语义匹配">
                {match?.semantic_score?.toFixed(1) ?? "-"}
              </Descriptions.Item>
              <Descriptions.Item label="LLM 推理">
                {match?.llm_score?.toFixed(1) ?? "-"}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} md={16}>
          <ChartCard
            option={radarOption}
            height={320}
            loading={loading}
          />
        </Col>
      </Row>

      <Row gutter={24} style={{ marginTop: 24 }}>
        <Col span={24}>
          <Card title="各维度评分">
            <Descriptions column={{ xs: 2, sm: 3, md: 4, lg: 7 }} size="small" bordered>
              <Descriptions.Item label="学历匹配">
                <ScoreTag score={match?.dimension_scores.education ?? 0} />
              </Descriptions.Item>
              <Descriptions.Item label="技能匹配">
                <ScoreTag score={match?.dimension_scores.skills ?? 0} />
              </Descriptions.Item>
              <Descriptions.Item label="经验匹配">
                <ScoreTag score={match?.dimension_scores.experience ?? 0} />
              </Descriptions.Item>
              <Descriptions.Item label="证书匹配">
                <ScoreTag score={match?.dimension_scores.certifications ?? 0} />
              </Descriptions.Item>
              <Descriptions.Item label="语言能力">
                <ScoreTag score={match?.dimension_scores.languages ?? 0} />
              </Descriptions.Item>
              <Descriptions.Item label="地点匹配">
                <ScoreTag score={match?.dimension_scores.location ?? 0} />
              </Descriptions.Item>
              <Descriptions.Item label="综合得分">
                <ScoreTag score={match?.dimension_scores.overall ?? 0} />
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Row gutter={24} style={{ marginTop: 24 }}>
        <Col xs={24} md={12}>
          <Card
            title={
              <span>
                <CheckCircleOutlined style={{ color: "#52c41a" }} /> 已匹配技能
              </span>
            }
          >
            {match?.is_hard_pass ? (
              <Text type="secondary">硬性条件未通过，未进行技能匹配</Text>
            ) : (match?.matched_skills?.length ?? 0) > 0 ? (
              <div>
                {match?.matched_skills.map((s, i) => (
                  <Tag key={i} color="green" style={{ margin: 4 }}>
                    {s}
                  </Tag>
                ))}
              </div>
            ) : (
              <Text type="secondary">暂无</Text>
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card
            title={
              <span>
                <CloseCircleOutlined style={{ color: "#f5222d" }} /> 缺失技能
              </span>
            }
          >
            {match?.is_hard_pass ? (
              <Tag color="red">未通过</Tag>
            ) : (match?.missing_skills?.length ?? 0) > 0 ? (
              <div>
                {match?.missing_skills.map((s, i) => (
                  <Tag key={i} color="red" style={{ margin: 4 }}>
                    {s}
                  </Tag>
                ))}
              </div>
            ) : (
              <Text type="success">所有要求技能均已匹配！</Text>
            )}
          </Card>
        </Col>
      </Row>

      {match?.llm_reasoning && (
        <Card title="AI 分析详情" style={{ marginTop: 24 }}>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>
            {match.llm_reasoning}
          </div>
        </Card>
      )}

      {(match?.suggestions?.length ?? 0) > 0 && (
        <Card
          title={
            <span>
              <BulbOutlined style={{ color: "#faad14" }} /> 优化建议
            </span>
          }
          style={{ marginTop: 24 }}
        >
          <List
            dataSource={match?.suggestions}
            renderItem={(item, i) => (
              <List.Item>
                <Text>
                  {i + 1}. {item}
                </Text>
              </List.Item>
            )}
          />
        </Card>
      )}
    </div>
  );
}
