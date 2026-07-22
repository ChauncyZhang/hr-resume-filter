# BeyondCandidate 企业部署仓库

本仓库只保存 Aurora 企业部署配置、生产发布脚本和内部操作文档。通用产品源码来自公开仓库 `beyondcandidate`，固定在 `product/` Git submodule 中。

## 首次克隆

```powershell
git clone --recurse-submodules git@github.com:ChauncyZhang/hr-resume-filter.git
cd hr-resume-filter
```

如果普通克隆时没有拉取子模块：

```powershell
git submodule update --init --recursive
```

## 日常开发与同步

通用功能、Bug 修复、前后端和数据库迁移统一在 `product/` 中修改，并提交到公开仓库。随后在本仓库更新并提交子模块指针：

```powershell
.\更新公共代码.ps1
git add product
git commit -m "Update BeyondCandidate product"
git push
```

企业域名、服务器、证书、共享 Nginx 和内部文档只在本仓库修改，禁止复制到 `product/`。

## 验证与部署

```powershell
.\验证代码.ps1
.\部署到生产.ps1
```

部署目标配置位于 `deploy/target.psd1`，不含密码或 API Key。已有服务器会执行版本化发布、健康检查和失败回滚；全新服务器会先检查 Docker、TLS 文件和企业共享网站前置条件，再生成独立密钥和初始管理员。

全新机器第一次部署前，只需准备以下外部条件：

1. 域名已经解析到新服务器，安全组开放 443。
2. 官网容器 `aurora-web` 已运行，部署脚本只把它接入共享网络，不修改或重启官网。
3. 将证书和私钥放在本机，并在被 Git 忽略的 `deploy/target.local.psd1` 中填写路径。

首次部署可显式使用本地目标配置：

```powershell
.\部署到生产.ps1 -ConfigPath .\deploy\target.local.psd1
```

脚本会自动安装 Docker（目前支持 apt 系 Linux）、生成生产密钥、创建初始管理员、执行数据库迁移和健康检查。初始密码只在首次初始化时显示一次。

## 目录

- `product/`：公开产品源码，只通过子模块同步。
- `deploy/`：Aurora 私有部署、回滚、Nginx 保护和服务器初始化。
- `internal-docs/`：内部 HR 与用人经理文档。

生产密钥只存在于服务器的权限受限环境文件中，不得提交到 Git。
