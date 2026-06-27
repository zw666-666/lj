CREATE DATABASE IF NOT EXISTS lvjing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE lvjing;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(20) UNIQUE COMMENT '手机号',
    email VARCHAR(255) UNIQUE COMMENT '邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    nickname VARCHAR(100) COMMENT '昵称',
    avatar_url VARCHAR(500) COMMENT '头像URL',
    license_no VARCHAR(50) COMMENT '执业证号',
    law_firm VARCHAR(200) COMMENT '所在律所',
    expertise TEXT COMMENT '擅长领域(JSON数组)',
    role ENUM('normal', 'premium', 'admin') DEFAULT 'normal' COMMENT '用户角色',
    trial_end_date DATETIME COMMENT '试用期结束日期',
    is_locked BOOLEAN DEFAULT FALSE COMMENT '是否锁定',
    login_attempts INT DEFAULT 0 COMMENT '连续登录失败次数',
    locked_until DATETIME COMMENT '锁定到期时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_phone (phone),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Refresh Token 表
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    token VARCHAR(500) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_token (token),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 裁判文书表
CREATE TABLE IF NOT EXISTS cases (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(100) UNIQUE COMMENT '案号',
    title VARCHAR(500) COMMENT '案件名称',
    court VARCHAR(200) COMMENT '审理法院',
    court_level ENUM('basic', 'intermediate', 'high', 'supreme') COMMENT '法院层级',
    court_region VARCHAR(100) COMMENT '法院地域',
    judge_name VARCHAR(100) COMMENT '承办法官',
    trial_procedure ENUM('first', 'second', 'retrial', 'supervision') COMMENT '审判程序',
    case_category_1 VARCHAR(100) COMMENT '一级案由',
    case_category_2 VARCHAR(100) COMMENT '二级案由',
    case_category_3 VARCHAR(100) COMMENT '三级案由',
    judgment_date DATE COMMENT '裁判日期',
    full_text LONGTEXT COMMENT '判决书全文',
    summary TEXT COMMENT 'AI案情概要',
    ruling_abstract TEXT COMMENT 'AI裁判要旨',
    tags JSON COMMENT '主题标签',
    processing_status ENUM('pending','summarizing','classifying','extracting','linking','completed','failed')
        DEFAULT 'pending' COMMENT 'AI处理状态',
    confidence_score DECIMAL(5,4) DEFAULT 0 COMMENT 'AI置信度',
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_case_no (case_no),
    INDEX idx_court (court),
    INDEX idx_judge (judge_name),
    INDEX idx_procedure (trial_procedure),
    INDEX idx_date (judgment_date),
    INDEX idx_category (case_category_2),
    INDEX idx_status (processing_status),
    FULLTEXT INDEX ft_full_text (full_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 争议焦点表
CREATE TABLE IF NOT EXISTS dispute_focuses (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    focus_name VARCHAR(300) NOT NULL COMMENT '焦点名称',
    plaintiff_claim TEXT COMMENT '原告主张',
    defendant_defense TEXT COMMENT '被告抗辩',
    court_finding TEXT COMMENT '法院认定',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 法律实体（当事人、法条等）
CREATE TABLE IF NOT EXISTS legal_entities (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    entity_type ENUM('party','court','judge','article','rule','other') COMMENT '实体类型',
    entity_name VARCHAR(300) NOT NULL COMMENT '实体名称',
    entity_detail JSON COMMENT '实体详情',
    confidence DECIMAL(5,4) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_case (case_id),
    INDEX idx_type (entity_type),
    INDEX idx_name (entity_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 裁判规则表
CREATE TABLE IF NOT EXISTS legal_rules (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    rule_text TEXT NOT NULL COMMENT '规范化的规则语句',
    rule_type ENUM('establish','extend','restrict','conflict','confirm') COMMENT '规则类型',
    related_article VARCHAR(300) COMMENT '关联法条',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_case (case_id),
    FULLTEXT INDEX ft_rule (rule_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 案例关联表（图谱边）
CREATE TABLE IF NOT EXISTS case_relations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_case_id BIGINT NOT NULL,
    target_case_id BIGINT NOT NULL,
    relation_type ENUM('similar','inherit','cite','cited_by','conflict','same_category') COMMENT '关联类型',
    relation_detail TEXT COMMENT '关联说明',
    confidence DECIMAL(5,4) DEFAULT 0,
    is_confirmed BOOLEAN DEFAULT FALSE COMMENT '管理员确认',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_case_id) REFERENCES cases(id) ON DELETE CASCADE,
    FOREIGN KEY (target_case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_source (source_case_id),
    INDEX idx_target (target_case_id),
    INDEX idx_type (relation_type),
    UNIQUE KEY uk_relation (source_case_id, target_case_id, relation_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 法官画像表
CREATE TABLE IF NOT EXISTS judge_profiles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    judge_name VARCHAR(100) NOT NULL UNIQUE,
    court VARCHAR(200) COMMENT '法院',
    division VARCHAR(200) COMMENT '审判庭',
    total_cases INT DEFAULT 0 COMMENT '审理案件总数',
    avg_duration_days DECIMAL(10,2) COMMENT '平均审理周期(天)',
    support_plaintiff_ratio DECIMAL(5,4) COMMENT '支持原告比例',
    support_defendant_ratio DECIMAL(5,4) COMMENT '支持被告比例',
    partial_support_ratio DECIMAL(5,4) COMMENT '部分支持比例',
    appeal_reversal_ratio DECIMAL(5,4) COMMENT '二审改判率',
    reversed_by_superior_ratio DECIMAL(5,4) COMMENT '被上级法院改判率',
    avg_opinion_length INT COMMENT '平均裁判意见字数',
    top_articles JSON COMMENT '高频援引法条Top10',
    case_type_distribution JSON COMMENT '案件类型分布',
    style_tags JSON COMMENT '论证风格标签',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_judge (judge_name),
    INDEX idx_court (court)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 收藏表
CREATE TABLE IF NOT EXISTS favorites (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    case_id BIGINT NOT NULL,
    personal_tags JSON COMMENT '个人标签',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    UNIQUE KEY uk_user_case (user_id, case_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 笔记表
CREATE TABLE IF NOT EXISTS notes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    case_id BIGINT NOT NULL,
    paragraph_ref VARCHAR(100) COMMENT '段落引用',
    entity_ref VARCHAR(300) COMMENT '实体引用',
    content TEXT NOT NULL COMMENT '笔记内容(Markdown)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_user_case (user_id, case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 案例分组表
CREATE TABLE IF NOT EXISTS case_groups (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    group_name VARCHAR(200) NOT NULL COMMENT '分组名称',
    description TEXT COMMENT '描述',
    sort_order INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_group_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    group_id BIGINT NOT NULL,
    case_id BIGINT NOT NULL,
    sort_order INT DEFAULT 0,
    FOREIGN KEY (group_id) REFERENCES case_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    UNIQUE KEY uk_group_case (group_id, case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 问答历史表
CREATE TABLE IF NOT EXISTS qa_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    session_title VARCHAR(300) COMMENT '会话标题',
    knowledge_scope JSON COMMENT '知识范围',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS qa_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id BIGINT NOT NULL,
    role ENUM('user','assistant') NOT NULL,
    content TEXT NOT NULL,
    citations JSON COMMENT '引用来源',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES qa_sessions(id) ON DELETE CASCADE,
    INDEX idx_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 通知表
CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(300) NOT NULL,
    content TEXT,
    notify_type ENUM('processing_done','new_case','new_judgment','system') NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    ref_id BIGINT COMMENT '关联ID(案例/法官等)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_unread (user_id, is_read)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 处理日志表
CREATE TABLE IF NOT EXISTS processing_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_id BIGINT NOT NULL,
    stage ENUM('summarizing','classifying','extracting','linking') NOT NULL,
    status ENUM('processing','success','failed','retrying') NOT NULL,
    error_message TEXT,
    dify_workflow_run_id VARCHAR(100),
    retry_count INT DEFAULT 0,
    started_at DATETIME,
    completed_at DATETIME,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_case_stage (case_id, stage)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 订阅方案表
CREATE TABLE IF NOT EXISTS subscription_plans (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '方案名称',
    plan_type ENUM('monthly','yearly') NOT NULL COMMENT '周期类型',
    price_cents INT NOT NULL COMMENT '价格(分)',
    original_price_cents INT COMMENT '原价(分),用于展示折扣',
    is_active BOOLEAN DEFAULT TRUE,
    features JSON COMMENT '方案权益描述',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户订阅表
CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    plan_id BIGINT NOT NULL,
    status ENUM('active','expired','cancelled','pending') DEFAULT 'pending',
    started_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    auto_renew BOOLEAN DEFAULT FALSE,
    cancelled_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES subscription_plans(id),
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 支付订单表
CREATE TABLE IF NOT EXISTS payment_orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    plan_id BIGINT NOT NULL,
    order_no VARCHAR(64) UNIQUE NOT NULL COMMENT '商户订单号',
    alipay_trade_no VARCHAR(64) COMMENT '支付宝交易号',
    amount_cents INT NOT NULL COMMENT '金额(分)',
    status ENUM('pending','paid','expired','refunded','failed') DEFAULT 'pending',
    payment_method VARCHAR(20) DEFAULT 'alipay',
    paid_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_order_no (order_no),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 每日用量统计表
CREATE TABLE IF NOT EXISTS usage_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    usage_date DATE NOT NULL,
    qa_count INT DEFAULT 0 COMMENT '当日问答次数',
    UNIQUE KEY uk_user_date (user_id, usage_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- users 表字段追加（如果表已存在则修改）
-- ALTER TABLE users ADD COLUMN subscription_expires_at DATETIME COMMENT '订阅到期时间';
-- ALTER TABLE users ADD COLUMN lifetime_export_count INT DEFAULT 0 COMMENT '终身导出次数';
