<template>
  <n-modal :show="visible" @update:show="(v: boolean) => !v && close()">
    <n-card :bordered="false" style="width:420px;max-width:90vw" title-style="font-size:16px;font-weight:600">
      <template #header>
        <span>{{ isEdit ? t('signature.editTitle') : t('signature.addTitle') }}</span>
      </template>
      <n-form label-placement="left" label-width="90" size="small">
        <n-form-item :label="t('signature.configName')">
          <n-input v-model:value="form.name" :placeholder="t('signature.configNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('signature.keystorePath')">
          <div style="display:flex;gap:8px;width:100%">
            <n-input v-model:value="form.path" readonly style="flex:1" />
            <n-button size="small" secondary @click="selectKeystoreFile">
              {{ t('signature.choose') }}
            </n-button>
          </div>
        </n-form-item>
        <n-form-item :label="t('signature.alias')">
          <n-input v-model:value="form.alias" />
        </n-form-item>
        <n-form-item :label="t('signature.storePassword')">
          <n-input v-model:value="form.storepass" type="password" />
        </n-form-item>
        <n-form-item :label="t('signature.keyPassword')">
          <n-input v-model:value="form.keypass" type="password" :placeholder="t('signature.keyPasswordPlaceholder')" />
        </n-form-item>
      </n-form>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
        <n-button size="small" secondary @click="close">{{ t('signature.cancel') }}</n-button>
        <n-button size="small" type="primary" @click="save">{{ t('signature.save') }}</n-button>
      </div>
    </n-card>
  </n-modal>
</template>

<script setup lang="ts">
import { reactive, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import serviceManager from '@services/ServiceManager'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  data?: any
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  save: [data: any]
}>()

const form = reactive({
  id: '',
  name: '',
  path: '',
  alias: '',
  storepass: '',
  keypass: '',
})

const isEdit = computed(() => !!form.id)

watch(() => props.visible, (newVal) => {
  if (newVal) {
    if (props.data) {
      Object.assign(form, props.data)
    } else {
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
    alert(t('signature.fillRequired'))
    return
  }
  emit('save', { ...form })
  close()
}

const selectKeystoreFile = async () => {
  try {
    const systemSvc = await serviceManager.getService('system') as any
    const res = await systemSvc.selectFile({
      title: t('signature.selectKeystore'),
      filters: [{ name: t('signature.keystoreFiles'), extensions: ['jks', 'keystore'] }],
    })
    if (res && !res.canceled) {
      const p = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
      if (p) form.path = p
    }
  } catch (error) {
    console.error(error)
  }
}
</script>
