"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Card,
  Table,
  Tag,
  Button,
  Select,
  message,
  Modal,
  Form,
  Switch,
  Space,
} from "antd";
import {
  EyeOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  listResumes,
  listJobs,
  matchResume,
  listMatchResults,
  deleteMatchResult,
} from "@/lib/api";
import type { MatchResult, ResumeItem, JDItem } from "@/lib/types";
import { PageHeader, ScoreTag, ConfirmButton, EmptyState, ErrorState } from "@/components";
import useApi from "@/hooks/useApi";

export default function ReportsPage() {
  const router = useRouter();
  const [matchOpen, setMatchOpen] = useState(false);
  const [matching, setMatching] = useState(false);
  const [matchForm] = Form.useForm();

  const { data: matches, loading, error, refresh } = useApi<MatchResult[]>(
    () => listMatchResults().then((d) => d.items)
  );

  // Supplementary data — non-critical; table degrades gracefully if these fail
  const { data: resumes } = useApi<ResumeItem[]>(() =>
    listResumes({ page_size: 100 }).then((d) =>
      d.items.filter((r) => r.parse_status === "completed")
    )
  );

  const { data: jobs } = useApi<JDItem[]>(() =>
    listJobs({ page_size: 100 }).then((d) =>
      d.items.filter((j) => j.parse_status === "completed")
    )
  );

  if (error && !loading) {
    return <ErrorState message={error} onRetry={refresh} />;
  }

  async function handleMatch(values: {
    resume_id: string;
    job_id: string;
    enable_llm: boolean;
  }) {
    setMatchOpen(false);
    setMatching(true);
    try {
      const result = await matchResume({
        resume_id: values.resume_id,
        job_id: values.job_id,
        enable_llm: values.enable_llm,
      });
      message.success(
        result.is_hard_pass
          ? "硬性条件不满足，匹配完成"
          : `匹配完成，综合得分: ${result.overall_score}/10`
      );
      refresh();
    } catch (e: any) {
      message.error(`匹配失败: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setMatching(false);
    }
  }

  function openMatchModal() {
    matchForm.resetFields();
    matchForm.setFieldValue("enable_llm", true);
    setMatchOpen(true);
  }

  async function handleDelete(id: string) {
    try {
      await deleteMatchResult(id);
      message.success("删除成功");
      refresh();
    } catch (e: any) {
      message.error(`删除失败: ${e?.response?.data?.detail || e.message}`);
    }
  }

  function formatDate(iso: string) {
    return iso?.replace("T", " ")?.slice(0, 19);
  }

  const columns = [
    {
      title: "简历",
      key: "resume",
      ellipsis: true,
      render: (_: unknown, record: MatchResult) => {
        const r = resumes?.find((x) => x.id === record.resume_id);
        return r?.original_filename || record.resume_id?.slice(0, 8);
      },
    },
    {
      title: "岗位",
      key: "job",
      ellipsis: true,
      render: (_: unknown, record: MatchResult) => {
        const j = jobs?.find((x) => x.id === record.job_id);
        return j?.title || record.job_id?.slice(0, 8);
      },
    },
    {
      title: "综合得分",
      dataIndex: "overall_score",
      key: "score",
      width: 120,
      render: (s: number) => <ScoreTag score={s} />,
      sorter: (a: MatchResult, b: MatchResult) =>
        a.overall_score - b.overall_score,
    },
    {
      title: "硬性条件",
      dataIndex: "is_hard_pass",
      key: "hard",
      width: 100,
      render: (v: boolean) =>
        v ? <Tag color="red">未通过</Tag> : <Tag color="green">通过</Tag>,
    },
    {
      title: "匹配时间",
      dataIndex: "created_at",
      key: "date",
      width: 160,
      render: (d: string) => formatDate(d),
    },
    {
      title: "操作",
      key: "actions",
      width: 160,
      render: (_: unknown, record: MatchResult) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => router.push(`/match/${record.id}`)}
          >
            详情
          </Button>
          <ConfirmButton
            type="link"
            title="确认删除"
            content="删除后无法恢复，确定要删除这条匹配报告吗？"
            onConfirm={() => handleDelete(record.id)}
          >
            删除
          </ConfirmButton>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="匹配报告"
        extra={
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={openMatchModal}
          >
            新建匹配
          </Button>
        }
      />

      <Card>
        <Table
          dataSource={matches || []}
          columns={columns}
          rowKey="id"
          loading={loading || matching}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条匹配记录` }}
          locale={{
            emptyText: (
              <EmptyState
                title="暂无匹配结果"
                description="选择一个简历和一个岗位开始匹配分析"
                actionLabel="新建匹配"
                onAction={openMatchModal}
              />
            ),
          }}
        />
      </Card>

      <Modal
        title="新建匹配分析"
        open={matchOpen}
        onCancel={() => setMatchOpen(false)}
        onOk={() => matchForm.submit()}
        width={520}
      >
        <Form
          form={matchForm}
          layout="vertical"
          onFinish={handleMatch}
          initialValues={{ enable_llm: true }}
        >
          <Form.Item
            name="resume_id"
            label="选择简历"
            rules={[{ required: true, message: "请选择简历" }]}
          >
            <Select
              placeholder="选择一份已解析的简历"
              showSearch
              optionFilterProp="label"
              options={(resumes || []).map((r) => ({
                value: r.id,
                label: `${r.original_filename} (${r.file_type.toUpperCase()})`,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="job_id"
            label="选择岗位"
            rules={[{ required: true, message: "请选择岗位" }]}
          >
            <Select
              placeholder="选择一个已解析的岗位"
              showSearch
              optionFilterProp="label"
              options={(jobs || []).map((j) => ({
                value: j.id,
                label: `${j.title}${j.department ? ` - ${j.department}` : ""}`,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="enable_llm"
            label="启用 LLM 深度推理"
            valuePropName="checked"
            extra="启用后匹配更准确，但耗时更长且会产生 API 费用"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
