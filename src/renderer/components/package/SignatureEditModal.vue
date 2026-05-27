<template>
  <div v-if="visible" class="modal-overlay">
     <div class="modal-content">
        <h3>{{ isEdit ? '编辑签名配置' : '新增签名配置' }}</h3>
        <div class="form-group">
           <label>配置名称:</label>
           <input v-model="form.name" type="text" placeholder="例如: Release Key" class="form-control">
        </div>
        <div class="form-group">
           <label>Keystore路径:</label>
           <div class="input-group">
              <input v-model="form.path" type="text" class="form-control" readonly>
              <button class="btn btn-secondary" @click="selectKeystoreFile">选择</button>
           </div>
        </div>
        <div class="form-group">
           <label>Alias (别名):</label>
           <input v-model="form.alias" type="text" class="form-control">
        </div>
        <div class="form-group">
           <label>Store Password:</label>
           <input v-model="form.storepass" type="password" class="form-control">
        </div>
        <div class="form-group">
           <label>Key Password:</label>
           <input v-model="form.keypass" type="password" class="form-control" placeholder="留空则同Store Password">
        </div>
        <div class="modal-actions">
           <button class="btn btn-secondary" @click="close">取消</button>
           <button class="btn btn-primary" @click="save">保存</button>
        </div>
     </div>
  </div>
</template>

<script>
import { ref, reactive, watch, computed } from 'vue'
import serviceManager from '@services/ServiceManager'

export default {
  name: 'SignatureEditModal',
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    data: {
      type: Object,
      default: () => null
    }
  },
  emits: ['update:visible', 'save'],
  setup(props, { emit }) {
    const form = reactive({
      id: '',
      name: '',
      path: '',
      alias: '',
      storepass: '',
      keypass: ''
    })

    const isEdit = computed(() => !!form.id)

    watch(() => props.visible, (newVal) => {
      if (newVal) {
        if (props.data) {
          Object.assign(form, props.data)
        } else {
          // Reset form
          form.id = ''
          form.name = ''
          form.path = ''
          form.alias = ''
          form.storepass = ''
          form.keypass = ''
        }
      }
    })

    const close = () => {
      emit('update:visible', false)
    }

    const save = () => {
       if (!form.name || !form.path || !form.alias) {
           alert('请填写必要信息(名称、路径、别名)')
           return
       }
       emit('save', { ...form })
       close()
    }

    const selectKeystoreFile = async () => {
        try {
        const systemSvc = await serviceManager.getService('system')
        const res = await systemSvc.selectFile({
          title: '选择Keystore文件',
          filters: [{ name: 'Keystore Files', extensions: ['jks', 'keystore'] }]
        })
        if (res && !res.canceled) {
            const p = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
            if (p) {
                form.path = p
            }
        }
      } catch (error) {
         console.error(error)
      }
    }

    return {
      form,
      isEdit,
      close,
      save,
      selectKeystoreFile
    }
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background: var(--card-bg);
  padding: 20px;
  border-radius: 8px;
  width: 400px;
  max-width: 90%;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  color: var(--text-primary);
}

.form-control {
  width: 100%;
  padding: 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.input-group {
  display: flex;
  gap: 8px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
</style>
