"use client";

import { useState } from "react";
import {
  Card,
  Upload,
  Button,
  Table,
  Tag,
  message,
  Space,
  Modal,
  Descriptions,
  Spin,
} from "antd";
import {
  InboxOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import type { UploadProps } from "antd";
import { uploadResume, listResumes, getResume, deleteResume } from "@/lib/api";
import type { ResumeItem, ResumeDetail } from "@/lib/types";
import { PageHeader, ConfirmButton, EmptyState, ErrorState } from "@/components";
import useApi from "@/hooks/useApi";

const { Dragger } = Upload;

const typeMap: Record<string, { color: string; label: string }> = {
  campus: { color: "blue", label: "🎓 校招" },
  experienced: { color: "green", label: "💼 社招" },
  unknown: { color: "default", label: "未知" },
};

const statusMap: Record<string, { color: string; label: string }> = {
  completed: { color: "green", label: "已完成" },
  processing: { color: "blue", label: "处理中" },
  pending: { color: "default", label: "等待中" },
  failed: { color: "red", label: "失败" },
};

export default function UploadPage() {
  const {
    data: resumes,
    loading,
    error,
    refresh,
  } = useApi<ResumeItem[]>(() =>
    listResumes({ page_size: 50 }).then((d) =>
      // 过滤掉失败记录——解析失败时后端已通过弹窗提示，列表中不需要展示
      d.items.filter((item) => item.parse_status !== "failed")
    )
  );

  const [detail, setDetail] = useState<ResumeDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  // 根据简历类型计算展示数据（安全处理 null）
  const isCampus = detail?.parsed_data?.resume_type === "campus";
  const detailInternships = detail?.parsed_data?.work_experience?.filter(
    (exp) => exp.employment_type === "internship" || exp.employment_type === "part-time"
  ) ?? [];
  const detailFullTime = detail?.parsed_data?.work_experience?.filter(
    (exp) => exp.employment_type !== "internship" && exp.employment_type !== "part-time"
  ) ?? [];
  const detailProjects = detail?.parsed_data?.projects ?? [];

  if (error && !loading) {
    return <ErrorState message={error} onRetry={refresh} />;
  }

  const uploadProps: UploadProps = {
    name: "file",
    multiple: true,
    accept: ".pdf,.docx,.doc,.txt,.md",
    showUploadList: false,
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        await uploadResume(file as File);
        message.success(`${(file as File).name} 上传成功`);
        onSuccess?.({});
        refresh();
      } catch (e: any) {
        const detail = e?.response?.data?.detail || e.message;
        message.error(`上传失败: ${detail}`);
        onError?.(e as Error);
      }
    },
  };

  async function handleView(id: string) {
    setDetailLoading(true);
    try {
      const data = await getResume(id);
      setDetail(data);
      setDetailOpen(true);
    } catch {
      message.error("获取简历详情失败");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleDelete(id: string) {
    await deleteResume(id);
    message.success("删除成功");
    refresh();
  }

  const columns = [
    {
      title: "文件名",
      dataIndex: "original_filename",
      key: "name",
      ellipsis: true,
    },
    {
      title: "格式",
      dataIndex: "file_type",
      key: "type",
      width: 80,
      render: (t: string) => <Tag>{t.toUpperCase()}</Tag>,
    },
    {
      title: "类型",
      dataIndex: "resume_type",
      key: "type",
      width: 90,
      render: (t: string) => {
        const info = typeMap[t] || typeMap.unknown;
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: "状态",
      dataIndex: "parse_status",
      key: "status",
      width: 100,
      render: (s: string) => {
        const info = statusMap[s] || { color: "default", label: s };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: "上传时间",
      dataIndex: "created_at",
      key: "date",
      width: 120,
      render: (d: string) => d?.slice(0, 10),
    },
    {
      title: "操作",
      key: "actions",
      width: 160,
      render: (_: unknown, record: ResumeItem) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => handleView(record.id)}
            disabled={record.parse_status !== "completed"}
          >
            查看
          </Button>
          <ConfirmButton
            type="link"
            title="确认删除"
            content="删除后无法恢复，确定要删除这份简历吗？"
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
      <PageHeader title="上传简历" />

      <Card style={{ marginBottom: 24 }}>
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽简历文件到此区域上传</p>
          <p className="ant-upload-hint">
            支持 PDF、DOCX、TXT、MD 格式，单文件不超过 10MB
          </p>
        </Dragger>
      </Card>

      <Card title="简历列表">
        <Table
          dataSource={resumes || []}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 份简历` }}
          locale={{ emptyText: <EmptyState title="暂无简历" description="上传第一份简历开始分析" /> }}
        />
      </Card>

      <Modal
        title="简历详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        width={800}
        footer={null}
      >
        {detailLoading ? (
          <Spin />
        ) : detail ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="姓名">
              {detail.parsed_data.basic_info.name || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="邮箱">
              {detail.parsed_data.basic_info.email || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="电话">
              {detail.parsed_data.basic_info.phone || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="城市">
              {detail.parsed_data.basic_info.city || "-"}
            </Descriptions.Item>

            {/* 社招显示工作年限，校招隐藏 */}
            {!isCampus && (
              <Descriptions.Item label="工作年限">
                {detail.parsed_data.basic_info.years_of_experience ?? "-"}
              </Descriptions.Item>
            )}

            <Descriptions.Item label="技能">
              {detail.parsed_data.skills.length > 0
                ? detail.parsed_data.skills.map((s) => (
                    <Tag key={s.name} color="blue">
                      {s.name}
                    </Tag>
                  ))
                : "-"}
            </Descriptions.Item>

            <Descriptions.Item label="教育背景">
              {detail.parsed_data.education.length > 0
                ? detail.parsed_data.education.map((edu, i) => (
                    <div key={i}>
                      {edu.school} | {edu.major} | {edu.degree}
                      {edu.gpa != null && ` | GPA ${edu.gpa}`}
                      {edu.expected_graduation && isCampus && (
                        <Tag color="orange" style={{ marginLeft: 8 }}>
                          🎓 预计 {edu.expected_graduation} 毕业
                        </Tag>
                      )}
                    </div>
                  ))
                : "-"}
            </Descriptions.Item>

            {/* 校招：实践经历（实习 + 项目）；社招：工作经历 */}
            {isCampus ? (
              <Descriptions.Item label="实践经历">
                {detailInternships.length > 0 || detailProjects.length > 0 ? (
                  <div>
                    {detailInternships.map((exp, i) => (
                      <div key={`intern-${i}`} style={{ marginBottom: 8 }}>
                        <Tag color="blue">实习</Tag>
                        <strong>{exp.title}</strong> @ {exp.company}
                        {exp.start_date && (
                          <span style={{ color: "#8c8c8c", marginLeft: 8 }}>
                            {exp.start_date} ~ {exp.end_date || "至今"}
                          </span>
                        )}
                        <br />
                        {exp.description?.slice(0, 200)}
                      </div>
                    ))}
                    {detailProjects.map((proj, i) => (
                      <div key={`proj-${i}`} style={{ marginBottom: 8 }}>
                        <Tag color="purple">项目</Tag>
                        <strong>{proj.name}</strong>
                        {proj.url && (
                          <a href={proj.url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 8 }}>
                            链接 ↗
                          </a>
                        )}
                        <br />
                        {proj.description?.slice(0, 200)}
                        {proj.tech_stack.length > 0 && (
                          <div style={{ marginTop: 4 }}>
                            {proj.tech_stack.map((tech) => (
                              <Tag key={tech} color="default" style={{ fontSize: 11 }}>
                                {tech}
                              </Tag>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  "-"
                )}
              </Descriptions.Item>
            ) : (
              <Descriptions.Item label="工作经历">
                {detailFullTime.length > 0
                  ? detailFullTime.map((exp, i) => (
                      <div key={i} style={{ marginBottom: 8 }}>
                        <strong>{exp.title}</strong> @ {exp.company}
                        <br />
                        {exp.description?.slice(0, 200)}
                      </div>
                    ))
                  : "-"}
              </Descriptions.Item>
            )}
          </Descriptions>
        ) : null}
      </Modal>
    </div>
  );
}
