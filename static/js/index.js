// index.js - 首页业务逻辑

/**
 * 加载大学内容
 * @param {string} mdPath - markdown文件路径
 */
async function loadUniversityContent(mdPath) {
    try {
        // 更新UI状态
        updateActiveLink(mdPath);
        showLoadingState();

        // 获取MD内容
        const response = await fetch(`/get_md_content?path=${encodeURIComponent(mdPath)}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '加载失败');
        }

        // 显示内容
        document.getElementById('welcome-content').style.display = 'none';
        const contentDiv = document.getElementById('university-content');
        contentDiv.innerHTML = data.content;
        contentDiv.style.display = 'block';

    } catch (error) {
        console.error('加载失败:', error);
        showError(error.message);
    }
}

/**
 * 更新当前选中的链接样式
 */
function updateActiveLink(mdPath) {
    // 移除所有active类
    document.querySelectorAll('#university-list .nav-link').forEach(link => {
        link.classList.remove('active');
    });

    // 添加active类到当前选中项
    const currentLink = document.querySelector(`[data-md-path="${mdPath}"]`);
    if (currentLink) {
        currentLink.classList.add('active');
    }
}

/**
 * 显示加载状态
 */
function showLoadingState() {
    const contentDiv = document.getElementById('university-content');
    contentDiv.style.display = 'block';
    contentDiv.innerHTML = '<div class="text-center my-5"><div class="spinner-border" role="status"></div><p class="mt-2">加载中...</p></div>';
}

/**
 * 显示错误信息
 */
function showError(message) {
    const contentDiv = document.getElementById('university-content');
    contentDiv.style.display = 'block';
    contentDiv.innerHTML = `
        <div class="alert alert-danger" role="alert">
            <h4 class="alert-heading">加载失败</h4>
            <p>${message}</p>
            <hr>
            <p class="mb-0">请刷新页面重试或联系管理员</p>
        </div>
    `;
}

// 页面加载完成后执行初始化
document.addEventListener('DOMContentLoaded', function() {
    // 为所有大学链接添加点击事件
    document.querySelectorAll('#university-list .nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault(); // 阻止默认的链接行为
        });
    });
});
