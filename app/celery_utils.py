# app/celery_utils.py
from celery import Celery

def make_celery(app):
    """
    为Flask应用创建一个配置好的Celery实例。
    """
    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL'],
        backend=app.config['CELERY_RESULT_BACKEND'],
        include=[] # 任务模块将由 celery_worker.py 导入
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery