function Card(viewModel) {
  <view backgroundColor="red">
    {viewModel.children()}
  </view>
}

<Card title={'hi'} {...rest}>
  <layout />
</Card>
